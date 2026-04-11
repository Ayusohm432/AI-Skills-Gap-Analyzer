import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { 
  User, Mail, Briefcase, Award, Save, 
  Loader2, CheckCircle2, AlertCircle, Plus, X 
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getProfileApi, updateProfileApi } from '../api/user';
import InteractiveBackground from '../components/InteractiveBackground';
import Navbar from '../components/Navbar';
import PageTransition from '../components/PageTransition';

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

  const [profile, setProfile] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [newSkill, setNewSkill] = useState('');

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await getProfileApi();
        setProfile(data);
      } catch (err) {
        console.error("Failed to fetch profile", err);
        setMessage({ type: 'error', text: 'Failed to load profile data.' });
        // Fallback to auth user if API fails
        setProfile({
          name: user?.name || '',
          email: user?.email || '',
          target_role: 'Not set',
          skills: []
        });
      } finally {
        setIsLoading(false);
      }
    };
    fetchProfile();
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setMessage({ type: '', text: '' });

    try {
      const updated = await updateProfileApi({
        name: profile.name,
        target_role: profile.target_role,
        skills: profile.skills
      });
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
                <motion.div {...fadeUp(0.1)} className="glass-card p-6 text-center">
                  <div className="w-24 h-24 rounded-full bg-gradient-to-br from-[var(--accent-warm)] to-[var(--accent-coral)] mx-auto mb-4 flex items-center justify-center shadow-lg">
                    <User size={40} className="text-white" />
                  </div>
                  <h2 className="text-lg font-bold text-[var(--text-primary)]">{profile.name || 'Anonymous'}</h2>
                  <p className="text-xs text-[var(--text-muted)] mb-4">{profile.email}</p>
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] text-[10px] font-bold uppercase tracking-wider">
                    Verified User
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
              </div>

              {/* Main Form */}
              <div className="md:col-span-2">
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
                      <label className="block text-sm font-medium text-[var(--text-secondary)] mb-3">
                        My Skills
                      </label>
                      <div className="flex flex-wrap gap-2 mb-4">
                        {profile.skills?.map((skill) => (
                          <span 
                            key={skill}
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
                          </span>
                        ))}
                        {profile.skills?.length === 0 && (
                          <p className="text-xs text-[var(--text-muted)] italic">No skills added yet. Add some below or run an analysis!</p>
                        )}
                      </div>
                      
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={newSkill}
                          onChange={(e) => setNewSkill(e.target.value)}
                          onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                          placeholder="Add a new skill (e.g. Python)"
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
                </motion.div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </PageTransition>
  );
}
