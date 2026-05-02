import React from 'react';
import { motion } from 'motion/react';
import { Lock, CheckCircle2 } from 'lucide-react';

export default function BadgeGrid({ badges }) {
  if (!badges || badges.length === 0) return null;

  return (
    <div className="glass-card p-6 border border-[var(--border-subtle)]">
      <h3 className="text-lg font-bold text-[var(--text-primary)] mb-6 flex items-center gap-2">
        <span className="text-xl">🏆</span> Achievement Badges
      </h3>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {badges.map((badge, idx) => (
          <motion.div
            key={badge.badge_id}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.05 }}
            className={`relative p-4 rounded-2xl flex flex-col items-center text-center transition-all duration-300 ${
              badge.earned
                ? 'bg-gradient-to-b from-[var(--bg-elevated)] to-[var(--bg-deep)] border border-[var(--accent-warm)]/30 hover:border-[var(--accent-warm)]/70 shadow-[0_4px_20px_rgba(232,168,73,0.1)]'
                : 'bg-[var(--bg-deep)] border border-[var(--border-subtle)] opacity-60 hover:opacity-100 grayscale hover:grayscale-0'
            }`}
          >
            {/* Icon Circle */}
            <div className={`w-14 h-14 rounded-full flex items-center justify-center text-3xl mb-3 shadow-inner ${
                badge.earned ? 'bg-[var(--bg-surface)]' : 'bg-[var(--bg-elevated)]'
            }`}>
              {badge.icon}
            </div>

            {/* Badge Info */}
            <h4 className="text-sm font-bold text-[var(--text-primary)] leading-tight mb-1">
              {badge.name}
            </h4>
            <p className="text-[10px] text-[var(--text-muted)] line-clamp-2 leading-tight">
              {badge.description}
            </p>

            {/* Status Indicator */}
            {badge.earned ? (
               <div className="absolute top-2 right-2 text-[var(--accent-teal)]">
                 <CheckCircle2 size={16} className="drop-shadow-sm" />
               </div>
            ) : (
               <div className="absolute top-2 right-2 text-[var(--text-muted)]">
                 <Lock size={14} />
               </div>
            )}
            
            {/* Earned Date Tooltip-like element */}
            {badge.earned && badge.awarded_at && (
                <div className="mt-2 text-[9px] font-medium text-[var(--accent-warm)] uppercase tracking-wider">
                    Earned {new Date(badge.awarded_at).toLocaleDateString()}
                </div>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
