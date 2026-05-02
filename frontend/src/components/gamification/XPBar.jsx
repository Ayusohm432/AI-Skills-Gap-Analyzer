import React from 'react';
import { motion } from 'motion/react';
import { Award } from 'lucide-react';

export default function XPBar({ progress }) {
  if (!progress) return null;

  const { level, total_xp, xp_to_next_level } = progress;
  // If xp_to_next_level is 0, they are max level. Let's assume a default scale otherwise
  const currentLevelXp = total_xp; // This is a simplification. Usually total_xp is cumulative.
  const nextLevelTotalXp = total_xp + xp_to_next_level;
  
  // Calculate percentage
  let percentage = 100;
  if (xp_to_next_level > 0) {
     // A simple visual representation: assuming they need 'xp_to_next_level' from their CURRENT total to level up.
     // For a true progress bar we'd need the base XP for the current level, but since backend doesn't provide it directly,
     // we can display progress towards the *next* milestone using an arbitrary visual scale.
     // For a better visual, let's just make the bar width proportional to XP gained in the current level vs needed.
     // Wait, the backend gives `xp_to_next_level`. Let's assume level XP requirement scales by 100 * level.
     const levelBaseXp = total_xp > 0 ? (total_xp / (total_xp + xp_to_next_level)) * 100 : 0;
     percentage = Math.max(5, Math.min(100, levelBaseXp));
  }

  return (
    <div className="glass-card p-6 border border-[var(--border-subtle)] relative overflow-hidden group">
      <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
        <Award size={80} className="text-[var(--accent-warm)]" />
      </div>
      
      <div className="flex justify-between items-end mb-3 relative z-10">
        <div>
          <h3 className="text-[var(--text-muted)] text-sm font-semibold uppercase tracking-wider mb-1 flex items-center gap-2">
            <Award size={14} className="text-[var(--accent-warm)]" />
            Current Level
          </h3>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-black text-[var(--text-primary)]">{level}</span>
            <span className="text-sm font-medium text-[var(--text-muted)]">
               ({total_xp.toLocaleString()} XP)
            </span>
          </div>
        </div>
        {xp_to_next_level > 0 && (
          <div className="text-right">
            <span className="text-xs text-[var(--text-muted)] font-medium">Next Level</span>
            <p className="text-sm font-bold text-[var(--text-primary)]">{xp_to_next_level.toLocaleString()} XP needed</p>
          </div>
        )}
      </div>

      <div className="w-full h-3 bg-[var(--bg-deep)] rounded-full overflow-hidden relative z-10 shadow-inner">
        <motion.div 
          className="h-full bg-gradient-to-r from-[var(--accent-warm)] to-[var(--accent-coral)]"
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
