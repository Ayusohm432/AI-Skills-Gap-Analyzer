import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  User, Mail, Briefcase, Award, Save, Camera,
  Loader2, CheckCircle2, AlertCircle, Plus, X, ChevronRight, Github, Clock, TrendingUp
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getProfileApi, updateProfileApi, getHistoryApi, disconnectGithubApi } from '../api/user';
import { getProgressApi, getBadgesApi, recordActionApi } from '../api/progress';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import PageTransition from '../components/PageTransition';
import XPBar from '../components/gamification/XPBar';
import StreakCard from '../components/gamification/StreakCard';
import BadgeGrid from '../components/gamification/BadgeGrid';
import GithubSync from '../components/GithubSync';
import { useNavigate } from 'react-router-dom';

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }
});

export default function ProfilePage() {
  const auth = useAuth();
  const { user, updateUserState } = auth;
  
  console.log("[ProfilePage] Rendered with auth context:", { 
    hasUser: !!user, 
    hasUpdateFunc: typeof updateUserState === 'function' 
  });

  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [history, setHistory] = useState([]);
  const [progress, setProgress] = useState(null);
  const [badges, setBadges] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [newSkill, setNewSkill] = useState('');
  const [avatarUrl, setAvatarUrl] = useState(null);
  const avatarInputRef = useRef(null);

  useEffect(() => {
    const initPage = async () => {
      try {
        const [profileData, historyData, progressData, badgesData] = await Promise.all([
          getProfileApi(),
          getHistoryApi(),
          getProgressApi().catch(() => null),
          getBadgesApi().catch(() => ({ badges: [] }))
        ]);
        setProfile(profileData);
        setHistory(historyData);
        setProgress(progressData);
        setBadges(badgesData.badges || []);
      } catch (err) {
        console.error("Failed to fetch initial profile data", err);
        setMessage({ type: 'error', text: 'Error loading some profile data.' });
        // Fallback for profile only
        if (!profile) {
           setProfile({
            name: user?.name || '',
            email: user?.email || '',
            target_role: 'Not set',
            skills: []
          });
        }
      } finally {
        setIsLoading(false);
      }
    };
    initPage();
  }, [user]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfile(prev => ({ ...prev, [name]: value }));
  };

  const addSkill = () => {
    if (newSkill.trim() && !profile.skills.includes(newSkill.trim())) {
      setProfile(prev => ({
        ...prev,
        skills: [...prev.skills, newSkill.trim()]
      }));
      setNewSkill('');
    }
  };

  const removeSkill = (skillToRemove) => {
    setProfile(prev => ({
      ...prev,
      skills: prev.skills.filter(s => s !== skillToRemove)
    }));
  };

  const handleAvatarChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAvatarUrl(reader.result);
    reader.readAsDataURL(file);
  };

  const handleGithubSyncComplete = async (mergedSkills, username) => {
    // Update local state with the new merged skills and username
    const updatedProfile = {
      ...profile,
      skills: mergedSkills,
      github_username: username
    };
    setProfile(updatedProfile);
    
    // Auto-save to backend
    try {
      setIsSaving(true);
      await updateProfileApi({
        name: updatedProfile.name,
        target_role: updatedProfile.target_role,
        skills: updatedProfile.skills,
        github_username: updatedProfile.github_username
      });
      setMessage({ type: 'success', text: 'GitHub profile synced and saved!' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Synced, but failed to save to profile.' });
    } finally {
      setIsSaving(false);
    }

    // Automatically trigger XP action for analyzing GitHub
    await recordActionApi('github_analyzed').catch(() => {});
    
    // Refresh Gamification stats to reflect new XP
    const [progressData, badgesData] = await Promise.all([
      getProgressApi().catch(() => null),
      getBadgesApi().catch(() => ({ badges: [] }))
    ]);
    if (progressData) setProgress(progressData);
    if (badgesData) setBadges(badgesData.badges || []);
  };

  const handleGithubDisconnect = async () => {
    try {
      setIsSaving(true);
      await disconnectGithubApi();
      
      const updatedProfile = {
        ...profile,
        github_username: null
      };
      setProfile(updatedProfile);
      
      setMessage({ type: 'success', text: 'GitHub profile disconnected.' });
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to disconnect GitHub.' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleViewAnalysis = (analysis) => {
    // Store the full analysis so DashboardPage can display it
    localStorage.setItem("analysisResult", JSON.stringify(analysis));
    // Also stamp the role from THIS analysis so any code reading
    // "userSelectedRole" gets the historically-correct role, not
    // whatever was left over from the last upload session.
    const role = analysis.predicted_role || analysis.target_role || "Auto Detect";
    localStorage.setItem("userSelectedRole", role);
    navigate("/dashboard");
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { 
      year: 'numeric', month: 'short', day: 'numeric' 
    });
  };

  const getScoreColor = (score) => {
    if (score >= 70) return 'text-[var(--accent-teal)]';
    if (score >= 40) return 'text-[var(--accent-warm)]';
    return 'text-[var(--accent-coral)]';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const updated = await updateProfileApi({
        name: profile.name,
        target_role: profile.target_role,
        skills: profile.skills,
        github_username: profile.github_username
      });
      
      // Award XP for updating profile/adding skills
      await recordActionApi('skill_added').catch(() => {});
      const [progressData, badgesData] = await Promise.all([
        getProgressApi().catch(() => null),
        getBadgesApi().catch(() => ({ badges: [] }))
      ]);
      if (progressData) setProgress(progressData);
      if (badgesData) setBadges(badgesData.badges || []);

      setProfile(updated);
      updateUserState(prev => ({ ...prev, name: updated.name }));
      setMessage({ type: 'success', text: 'Profile updated successfully!' });
    } catch (err) {
      setMessage({ type: 'error', text: err.message || 'Failed to update profile.' });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--bg-deep)] flex flex-col items-center justify-center text-[var(--text-muted)]">
        <Loader2 size={24} className="animate-spin mb-3 text-[var(--accent-warm)]" />
        <p className="text-sm">Loading your profile...</p>
      </div>
    );
  }

  const inputClass = "w-full px-4 py-3 rounded-xl bg-[var(--bg-deep)] border border-[var(--border-subtle)] text-[var(--text-primary)] placeholder-[var(--text-muted)] text-sm transition-all focus:border-[var(--accent-warm)]/50 focus:ring-1 focus:ring-[var(--accent-warm)]/20 outline-none";

  return (
    <PageTransition>
      <div className="min-h-screen relative flex flex-col">
        <InteractiveBackground />
        <Navbar />

        <main className="relative z-10 flex-1 pt-24 pb-12 px-6">
          <div className="max-w-4xl mx-auto">
            <motion.div {...fadeUp(0)} className="mb-10">
              <h1 className="text-3xl font-bold text-[var(--text-primary)] tracking-tight">User Profile</h1>
              <p className="text-[var(--text-muted)] text-sm mt-1.5">Manage your personal information and tracking skills.</p>
            </motion.div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {/* Sidebar Info */}
              <div className="md:col-span-1 space-y-6">
                <motion.div {...fadeUp(0.1)} className="glass-card p-6 text-center relative">
                {/* Avatar with upload */}
                <div className="relative w-24 h-24 mx-auto mb-4">
                  <div className="w-24 h-24 rounded-full bg-gradient-to-br from-[var(--accent-warm)] to-[var(--accent-coral)] flex items-center justify-center shadow-lg overflow-hidden">
                    {avatarUrl ? (
                      <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                    ) : (
                      <User size={40} className="text-white" />
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => avatarInputRef.current?.click()}
                    className="absolute bottom-0 right-0 w-7 h-7 rounded-full bg-[var(--accent-warm)] flex items-center justify-center shadow-md hover:scale-110 transition-transform"
                  >
                    <Camera size={13} className="text-black" />
                  </button>
                  <input ref={avatarInputRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
                </div>
                <h2 className="text-lg font-bold text-[var(--text-primary)]">{profile.name || 'Anonymous'}</h2>
                <p className="text-xs text-[var(--text-muted)] mb-4">{profile.email}</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <div className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] text-[10px] font-bold uppercase tracking-wider">
                    Verified User
                  </div>
                  {profile.github_username && (
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] text-[10px] font-bold uppercase tracking-wider">
                      <CheckCircle2 size={12} /> GitHub Connected
                    </div>
                  )}
                </div>
              </motion.div>

                <motion.div {...fadeUp(0.2)} className="glass-card p-6">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4 flex items-center gap-2">
                    <Award size={16} className="text-[var(--accent-teal)]" />
                    Stats Summary
                  </h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[var(--text-muted)]">Skills Tracked</span>
                      <span className="text-[var(--text-primary)] font-medium">{profile.skills?.length || 0}</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-[var(--text-muted)]">Analysis Count</span>
                      <span className="text-[var(--text-primary)] font-medium">{profile.analysis_history?.length || 0}</span>
                    </div>
                  </div>
                </motion.div>

                {/* Gamification Stats */}
                <motion.div {...fadeUp(0.25)}>
                  <StreakCard progress={progress} />
                </motion.div>
                
              </div>

              {/* Main Form */}
              <div className="md:col-span-2 space-y-8">
                
                <motion.div {...fadeUp(0.12)}>
                  <XPBar progress={progress} />
                </motion.div>

                {profile.github_username && (
                  <motion.div {...fadeUp(0.13)} className="px-4 py-3 rounded-xl bg-[var(--accent-teal-dim)] border border-[var(--accent-teal)]/20 text-[var(--accent-teal)] text-sm flex items-start gap-3">
                    <Github size={18} className="mt-0.5 shrink-0" />
                    <div>
                      <strong>Your GitHub account (@{profile.github_username}) is linked</strong> — your public repositories are being used to enrich your skill analysis.
                    </div>
                  </motion.div>
                )}

                <motion.div {...fadeUp(0.15)} className="glass-card p-8 noise-overlay">
                  {message.text && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className={`mb-6 p-4 rounded-xl flex items-center gap-3 text-sm ${
                        message.type === 'success' 
                          ? 'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)] border border-[var(--accent-teal)]/20' 
                          : 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)] border border-[var(--accent-coral)]/20'
                      }`}
                    >
                      {message.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                      {message.text}
                    </motion.div>
                  )}

                  <form onSubmit={handleSubmit} className="space-y-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                      {/* Name */}
                      <div>
                        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                          <User size={14} className="text-[var(--text-muted)]" />
                          Full Name
                        </label>
                        <input
                          type="text"
                          name="name"
                          value={profile.name || ''}
                          onChange={handleChange}
                          placeholder="Your Name"
                          className={inputClass}
                        />
                      </div>

                      {/* Email (Read Only) */}
                      <div>
                        <label className="block text-sm font-medium text-[var(--text-muted)] mb-2 flex items-center gap-2">
                          <Mail size={14} />
                          Email Address
                        </label>
                        <input
                          type="email"
                          value={profile.email}
                          disabled
                          className={`${inputClass} opacity-60 cursor-not-allowed border-transparent bg-[var(--bg-elevated)]`}
                        />
                      </div>
                    </div>

                    {/* Target Role */}
                    <div>
                      <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2 flex items-center gap-2">
                        <Briefcase size={14} className="text-[var(--text-muted)]" />
                        Target Career Role
                      </label>
                      <input
                        type="text"
                        name="target_role"
                        value={profile.target_role || ''}
                        onChange={handleChange}
                        placeholder="e.g. Senior Backend Developer"
                        className={inputClass}
                      />
                    </div>

                    {/* Skills Management */}
                    <div>
                      <label className="block text-sm font-medium text-[var(--text-secondary)] mb-3">My Skills</label>
                      <div className="flex flex-wrap gap-2 mb-4">
                        <AnimatePresence>
                          {profile.skills?.map((skill, idx) => (
                            <motion.span
                              key={skill}
                              initial={{ opacity: 0, scale: 0.7 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.7 }}
                              transition={{ type: 'spring', stiffness: 400, damping: 22, delay: idx * 0.03 }}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-sm rounded-lg hover:border-[var(--accent-coral)]/30 group transition-all"
                            >
                              {skill}
                              <button
                                type="button"
                                onClick={() => removeSkill(skill)}
                                className="text-[var(--text-muted)] hover:text-[var(--accent-coral)] transition-colors"
                              >
                                <X size={14} />
                              </button>
                            </motion.span>
                          ))}
                        </AnimatePresence>
                        {profile.skills?.length === 0 && (
                          <p className="text-xs text-[var(--text-muted)] italic">No skills added yet. Add some below or run an analysis!</p>
                        )}
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={newSkill}
                          onChange={(e) => setNewSkill(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                          placeholder="Add a skill (e.g. Python) and press Enter"
                          className={`${inputClass} flex-1`}
                        />
                        <button
                          type="button"
                          onClick={addSkill}
                          className="px-4 bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] rounded-xl hover:bg-[var(--bg-surface)] transition-colors"
                        >
                          <Plus size={18} />
                        </button>
                      </div>
                    </div>

                    <div className="pt-4 flex justify-end">
                      <motion.button
                        type="submit"
                        disabled={isSaving}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className="btn-warm px-8 py-3 flex items-center gap-2 disabled:opacity-60"
                      >
                        {isSaving ? (
                          <><Loader2 size={18} className="animate-spin" /> Saving...</>
                        ) : (
                          <><Save size={18} /> Save Changes</>
                        )}
                      </motion.button>
                    </div>
                  </form>

                  {/* GitHub Sync Section - Moved outside form to prevent nesting */}
                  <div className="mt-8 pt-8 border-t border-[var(--border-subtle)]">
                    <GithubSync 
                      currentSkills={profile.skills || []} 
                      currentUsername={profile.github_username}
                      onSyncComplete={handleGithubSyncComplete} 
                      onDisconnect={handleGithubDisconnect}
                    />
                  </div>
                </motion.div>
              </div>
            </div>

            {/* Gamification Badges */}
            <motion.div {...fadeUp(0.25)} className="mt-8">
               <BadgeGrid badges={badges} />
            </motion.div>

            {/* Analysis History — Vertical Timeline */}
            <motion.div {...fadeUp(0.3)} className="mt-12">
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h2 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight flex items-center gap-3">
                    <Clock size={22} className="text-[var(--accent-lavender)]" />
                    Activity Timeline
                  </h2>
                  <p className="text-[var(--text-muted)] text-sm mt-1">Your past skill gap assessments in chronological order.</p>
                </div>
                <div className="text-xs font-semibold px-3 py-1 rounded-full bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-muted)]">
                  {history?.length || 0} Reports
                </div>
              </div>

              {history && history.length > 0 ? (
                <div className="relative pl-8">
                  {/* Vertical timeline line */}
                  <div className="absolute left-3 top-2 bottom-2 w-px bg-gradient-to-b from-[var(--accent-lavender)] via-[var(--border-subtle)] to-transparent" />

                  <div className="space-y-6">
                    {history.map((item, idx) => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.3 + idx * 0.08, type: 'spring', stiffness: 260, damping: 22 }}
                        className="relative"
                      >
                        {/* Timeline dot */}
                        <div className={`absolute -left-[21px] top-4 w-3 h-3 rounded-full border-2 ${
                          idx === 0 ? 'bg-[var(--accent-lavender)] border-[var(--accent-lavender)]' : 'bg-[var(--bg-surface)] border-[var(--border-hover)]'
                        }`} />

                        <div className="glass-card p-5 hover:border-[var(--accent-lavender)]/30 transition-all group flex flex-col sm:flex-row sm:items-center gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="font-bold text-[var(--text-primary)] group-hover:text-[var(--accent-lavender)] transition-colors">
                                {item.target_role}
                              </h3>
                              {idx === 0 && (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[var(--accent-lavender-dim)] text-[var(--accent-lavender)] border border-[var(--accent-lavender)]/20">Latest</span>
                              )}
                            </div>
                            <p className="text-xs text-[var(--text-muted)] flex items-center gap-1.5">
                              <Clock size={10} />
                              {formatDate(item.created_at)}
                            </p>
                          </div>

                          <div className="flex items-center gap-4">
                            <div className="text-center">
                              <div className={`text-2xl font-black ${getScoreColor(item.readiness_score)}`}>
                                {Math.round(item.readiness_score)}%
                              </div>
                              <div className="text-[10px] text-[var(--text-muted)] font-medium">Readiness</div>
                            </div>
                            <button
                              onClick={() => handleViewAnalysis(item)}
                              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-xs font-semibold hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-all group/btn"
                            >
                              View <ChevronRight size={14} className="group-hover/btn:translate-x-0.5 transition-transform" />
                            </button>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="glass-card p-12 text-center border-dashed border-2">
                  <div className="w-16 h-16 rounded-2xl bg-[var(--bg-deep)] flex items-center justify-center mx-auto mb-4 border border-[var(--border-subtle)]">
                    <TrendingUp size={24} className="text-[var(--text-muted)]" />
                  </div>
                  <h3 className="text-[var(--text-primary)] font-bold mb-1">No activity yet</h3>
                  <p className="text-[var(--text-muted)] text-sm mb-6 max-w-xs mx-auto">Upload your first resume to start tracking your skill gaps and career growth.</p>
                  <button
                    onClick={() => navigate('/upload')}
                    className="inline-flex items-center gap-2 text-[var(--accent-warm)] text-sm font-semibold hover:underline"
                  >
                    Analyze your first resume <ChevronRight size={16} />
                  </button>
                </div>
              )}
            </motion.div>
          </div>
        </main>
      </div>
    </PageTransition>
  );
}
