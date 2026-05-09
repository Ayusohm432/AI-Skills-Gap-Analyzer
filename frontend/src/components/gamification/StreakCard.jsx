import React from 'react';
import { motion } from 'motion/react';
import { Flame } from 'lucide-react';

export default function StreakCard({ progress }) {
  if (!progress) return null;

  const { streak_days } = progress;
  const isActive = streak_days > 0;

  return (
    <div className={`glass-card p-6 border relative overflow-hidden group ${
        isActive ? 'border-[var(--accent-coral)]/30' : 'border-[var(--border-subtle)]'
    }`}>
      <div className={`absolute top-0 right-0 p-4 transition-opacity ${
          isActive ? 'opacity-10 group-hover:opacity-20 text-[var(--accent-coral)]' : 'opacity-5 text-[var(--text-muted)]'
      }`}>
        <Flame size={80} />
      </div>

      <div className="flex items-center gap-4 relative z-10">
        <div className={`w-14 h-14 rounded-full flex items-center justify-center shadow-lg ${
            isActive 
              ? 'bg-gradient-to-br from-[var(--accent-coral)] to-[#e55039]' 
              : 'bg-[var(--bg-deep)] border border-[var(--border-subtle)]'
        }`}>
          <Flame size={28} className={isActive ? 'text-white fill-white' : 'text-[var(--text-muted)]'} />
        </div>
        <div>
          <h3 className="text-[var(--text-muted)] text-sm font-semibold uppercase tracking-wider mb-0.5">
            Active Streak
          </h3>
          <div className="flex items-baseline gap-2">
            <span className={`text-4xl font-black ${isActive ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'}`}>
              {streak_days}
            </span>
            <span className="text-sm font-medium text-[var(--text-muted)]">
              {streak_days === 1 ? 'Day' : 'Days'}
            </span>
          </div>
        </div>
      </div>
      
      <p className="text-xs text-[var(--text-muted)] mt-4 relative z-10 font-medium">
        {isActive 
          ? "You're on fire! Complete an action tomorrow to keep it going." 
          : "Complete an analysis or add a skill to start your streak!"}
      </p>
    </div>
  );
}
