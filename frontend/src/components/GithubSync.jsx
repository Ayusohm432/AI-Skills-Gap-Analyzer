import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Github, Loader2, CheckCircle2, AlertCircle, ArrowRight } from 'lucide-react';
import { analyzeGithubApi } from '../api/github';

export default function GithubSync({ currentSkills, currentUsername, onSyncComplete, onDisconnect }) {
  const [username, setUsername] = useState('');
  const [isSyncing, setIsSyncing] = useState(false);
  const [result, setResult] = useState(null); // { type: 'success'|'error', text: '', details: null }

  const handleSync = async () => {
    if (!username.trim()) return;

    setIsSyncing(true);
    setResult(null);

    try {
      const data = await analyzeGithubApi(username.trim(), currentSkills);
      
      const newSkillsCount = data.merged_skills.length - currentSkills.length;
      
      setResult({
        type: 'success',
        text: `Successfully analyzed ${data.repos_analyzed} repositories!`,
        details: `Found ${data.github_skills.length} skills from GitHub. Added ${newSkillsCount > 0 ? newSkillsCount : 0} new skills to your profile.`
      });

      // Pass the merged skills and username back to the parent to update the state
      if (onSyncComplete) {
        onSyncComplete(data.merged_skills, username.trim());
      }
      
    } catch (err) {
      setResult({
        type: 'error',
        text: 'Failed to sync with GitHub',
        details: err.message
      });
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="glass-card p-6 border border-[var(--border-subtle)] relative overflow-hidden group">
      {/* Background Icon */}
      <div className="absolute -top-4 -right-4 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
        <Github size={120} />
      </div>

      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-[var(--bg-deep)] border border-[var(--border-subtle)] flex items-center justify-center text-[var(--text-primary)]">
            <Github size={20} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-[var(--text-primary)]">
              {currentUsername ? "GitHub Connected" : "Sync with GitHub"}
            </h3>
            <p className="text-xs text-[var(--text-muted)]">
              {currentUsername 
                ? `Connected as @${currentUsername}` 
                : "Enrich your profile with skills from public repos"}
            </p>
          </div>
        </div>

        {currentUsername ? (
          <div className="flex items-center justify-between p-4 bg-[var(--bg-deep)] border border-[var(--border-subtle)] rounded-xl mb-4">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={18} className="text-[var(--accent-teal)]" />
              <span className="text-sm font-medium text-[var(--text-primary)]">Profile Synced</span>
            </div>
            <button
              type="button"
              onClick={onDisconnect}
              className="text-xs font-semibold text-[var(--accent-coral)] hover:text-[#ff7675] hover:underline"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row gap-3 mb-4">
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSync()}
            placeholder="GitHub Username"
            className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--bg-deep)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-sm focus:border-[var(--accent-teal)]/50 focus:ring-1 focus:ring-[var(--accent-teal)]/20 outline-none transition-all"
            disabled={isSyncing}
          />
          <button
            type="button"
            onClick={handleSync}
            disabled={isSyncing || !username.trim()}
            className="px-5 py-2.5 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] text-sm font-semibold hover:border-[var(--accent-teal)] hover:text-[var(--accent-teal)] transition-all flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed group/btn"
          >
            {isSyncing ? (
              <><Loader2 size={16} className="animate-spin" /> Fetching...</>
            ) : (
              <>Sync <ArrowRight size={16} className="group-hover/btn:translate-x-0.5 transition-transform" /></>
            )}
          </button>
        </div>
        )}

        {/* Result Message */}
        {result && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            className={`p-4 rounded-xl text-sm border ${
              result.type === 'success'
                ? 'bg-[var(--accent-teal-dim)] border-[var(--accent-teal)]/20 text-[var(--accent-teal)]'
                : 'bg-[var(--accent-coral-dim)] border-[var(--accent-coral)]/20 text-[var(--accent-coral)]'
            }`}
          >
            <div className="flex items-center gap-2 font-semibold mb-1">
              {result.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
              {result.text}
            </div>
            {result.details && <p className="opacity-80 text-xs ml-6">{result.details}</p>}
          </motion.div>
        )}
      </div>
    </div>
  );
}
