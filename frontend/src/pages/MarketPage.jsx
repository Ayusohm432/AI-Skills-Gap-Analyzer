import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, 
  ResponsiveContainer, Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis 
} from 'recharts';
import { 
  TrendingUp, Users, DollarSign, Activity, AlertCircle, 
  Clock, MapPin, Building2, CheckCircle2, XCircle, Star, Briefcase
} from 'lucide-react';
import { secureFetch } from '../api/base';
import PageTransition from '../components/PageTransition';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';

// ── Helpers & Micro-Components ─────────────────────────────────────────────

const formatCurrency = (value, currency = 'INR') => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency, maximumFractionDigits: 0, notation: 'compact'
  }).format(value);
};

const useCounter = (end, duration = 1500) => {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (end === undefined || end === null) return;
    let startTimestamp = null;
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setCount(Math.floor(ease * end));
      if (progress < 1) window.requestAnimationFrame(step);
    };
    window.requestAnimationFrame(step);
  }, [end, duration]);
  return count;
};

const AnimatedCounter = ({ value, prefix = '', suffix = '' }) => {
  const count = useCounter(value);
  return <span>{prefix}{count.toLocaleString()}{suffix}</span>;
};

// Custom Tooltip for Area Chart
const CustomAreaTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-card p-3 shadow-xl text-sm border border-[var(--border-subtle)]">
        <p className="text-[var(--text-muted)] mb-2 font-medium">
          {new Date(label).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        </p>
        <p className="text-[var(--text-primary)] font-semibold flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--accent-lavender)]"></span>
          Demand Score: {payload[0].value}
        </p>
        {payload[1] && (
          <p className="text-[var(--text-primary)] font-semibold flex items-center gap-2 mt-1">
            <span className="w-2 h-2 rounded-full bg-[var(--accent-teal)]"></span>
            Postings: {payload[1].value.toLocaleString()}
          </p>
        )}
      </div>
    );
  }
  return null;
};

const SkeletonLoader = () => (
  <div className="animate-pulse space-y-6">
    <div className="h-40 bg-[var(--bg-elevated)] rounded-2xl w-full border border-[var(--border-subtle)]"></div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div className="h-32 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]"></div>
      <div className="h-32 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]"></div>
      <div className="h-32 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]"></div>
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="h-80 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]"></div>
      <div className="h-80 bg-[var(--bg-elevated)] rounded-xl border border-[var(--border-subtle)]"></div>
    </div>
  </div>
);

// ── Main Page Component ────────────────────────────────────────────────────

export default function MarketPage() {
  const [roles, setRoles] = useState([]);
  const [selectedRole, setSelectedRole] = useState('');
  
  const [demandData, setDemandData] = useState(null);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [companiesData, setCompaniesData] = useState(null);
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch roles list on mount
  useEffect(() => {
    secureFetch('/api/v1/market/roles')
      .then(r => r.ok ? r.json() : Promise.reject('Failed to fetch roles'))
      .then(data => {
        setRoles(data.roles);
        const savedRole = localStorage.getItem("userSelectedRole");
        if (savedRole && data.roles.includes(savedRole)) setSelectedRole(savedRole);
        else if (data.roles.length > 0) setSelectedRole(data.roles.find(r => r !== "Auto Detect") || data.roles[0]);
      })
      .catch(err => console.error(err));
  }, []);

  // Fetch market data when role changes
  useEffect(() => {
    if (!selectedRole || selectedRole === "Auto Detect") return;

    let isMounted = true;
    setIsLoading(true);
    setError(null);

    Promise.all([
      secureFetch(`/api/v1/market/demand?role=${encodeURIComponent(selectedRole)}`).then(r => r.ok ? r.json() : Promise.reject('Demand Data Error')),
      secureFetch(`/api/v1/market/benchmarks?role=${encodeURIComponent(selectedRole)}`).then(r => r.ok ? r.json() : null).catch(() => null),
      secureFetch(`/api/v1/market/companies?role=${encodeURIComponent(selectedRole)}`).then(r => r.ok ? r.json() : null).catch(() => null)
    ])
    .then(([demand, bench, comps]) => {
      if (!isMounted) return;
      setDemandData(demand);
      setBenchmarkData(bench);
      setCompaniesData(comps);
    })
    .catch(err => {
      if (!isMounted) return;
      setError("Unable to load market data for this role at the moment. Please try again later.");
    })
    .finally(() => {
      if (isMounted) setIsLoading(false);
    });

    return () => { isMounted = false; };
  }, [selectedRole]);

  // Framer Motion Variants
  const containerVars = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };
  const itemVars = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
  };

  // Data pre-processing
  const historyData = demandData ? [...(demandData.history || [])].reverse().map(h => ({
    date: h.captured_at, demand: h.demand_score, postings: h.total_postings
  })) : [];

  const radarData = [];
  if (benchmarkData && !benchmarkData.insufficient_data) {
    const topSkills = benchmarkData.top_skills || [];
    const userHas = benchmarkData.user_stats?.has_top_skills || [];
    topSkills.slice(0, 6).forEach(ts => {
      radarData.push({
        skill: ts.skill.length > 12 ? ts.skill.substring(0, 10) + '...' : ts.skill,
        fullSkill: ts.skill,
        "Market Avg": ts.freq_pct,
        "You": userHas.includes(ts.skill) ? 100 : 0
      });
    });
  }

  const missingSkills = benchmarkData?.user_stats?.missing_top_skills || [];

  return (
    <PageTransition>
      <Navbar />
      <div className="min-h-screen pt-24 pb-20 px-6 lg:px-8 max-w-7xl mx-auto space-y-8">
        
        {/* Role Tab Switcher */}
        <div className="flex overflow-x-auto pb-2 scrollbar-hide gap-2 mask-linear-fade">
          {roles.filter(r => r !== 'Auto Detect').map(role => (
            <button
              key={role}
              onClick={() => setSelectedRole(role)}
              className={`whitespace-nowrap px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-300 border ${
                selectedRole === role 
                ? 'bg-[var(--accent-lavender-dim)] text-[var(--accent-lavender)] border-[var(--accent-lavender)] shadow-[0_0_15px_rgba(143,111,246,0.15)]' 
                : 'bg-[var(--bg-surface)] text-[var(--text-secondary)] border-[var(--border-subtle)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]'
              }`}
            >
              {role}
            </button>
          ))}
        </div>

        {/* Loading / Error States */}
        {isLoading && <SkeletonLoader />}
        {error && !isLoading && (
          <div className="min-h-[40vh] flex items-center justify-center">
            <div className="glass-card border border-[var(--accent-coral)]/30 p-8 flex flex-col items-center text-center max-w-md">
              <AlertCircle className="text-[var(--accent-coral)] mb-4" size={48} />
              <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">Data Unavailable</h3>
              <p className="text-sm text-[var(--text-muted)]">{error}</p>
            </div>
          </div>
        )}

        {/* Main Dashboard */}
        {!isLoading && !error && demandData && (
          <motion.div variants={containerVars} initial="hidden" animate="show" className="space-y-6">
            
            {/* HERO BANNER */}
            <motion.div variants={itemVars} className="relative overflow-hidden rounded-2xl glass-card border border-[var(--border-subtle)] p-8 sm:p-10">
              <div className="absolute inset-0 bg-gradient-to-br from-[var(--accent-lavender)]/10 via-transparent to-[var(--accent-teal)]/5 pointer-events-none"></div>
              <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--accent-lavender)]/20 blur-[100px] rounded-full pointer-events-none transform translate-x-1/2 -translate-y-1/2"></div>
              
              <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <span className="px-3 py-1 rounded-full bg-[var(--accent-teal-dim)] border border-[var(--accent-teal)]/20 text-[var(--accent-teal)] text-xs font-bold uppercase tracking-widest flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-teal)] animate-pulse-soft"></span>
                      Live Market Data
                    </span>
                    <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] font-medium">
                      <Clock size={12} />
                      Updated {new Date(demandData.last_updated).toLocaleDateString()}
                    </span>
                  </div>
                  <h1 className="text-4xl sm:text-5xl font-extrabold text-[var(--text-primary)] tracking-tight">
                    {demandData.role}
                  </h1>
                  <p className="mt-3 text-[var(--text-secondary)] text-lg max-w-2xl">
                    Real-time hiring trends, salary expectations, and skill demands.
                  </p>
                </div>
              </div>
            </motion.div>

            {/* TOP METRICS GRID */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Demand Score */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl relative overflow-hidden group hover:-translate-y-1 transition-transform duration-300">
                <div className="absolute -right-6 -bottom-6 opacity-5 group-hover:opacity-10 transition-opacity transform group-hover:scale-110 duration-500">
                  <Activity size={120} className="text-[var(--accent-lavender)]" />
                </div>
                <p className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">Demand Score</p>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-5xl font-black text-[var(--text-primary)]">
                    <AnimatedCounter value={demandData.demand_score} />
                  </span>
                  <span className="text-lg text-[var(--text-muted)] font-medium">/ 100</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                    demandData.trend === 'rising' ? 'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]' :
                    demandData.trend === 'declining' ? 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)]' :
                    'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
                  }`}>
                    {demandData.trend === 'rising' ? '↑' : demandData.trend === 'declining' ? '↓' : '→'} {Math.abs(demandData.yoy_growth_pct)}% YoY
                  </span>
                  <span className="text-xs text-[var(--text-muted)] capitalize">{demandData.trend} Trend</span>
                </div>
              </motion.div>

              {/* Salary Range Visual */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl relative overflow-hidden group hover:-translate-y-1 transition-transform duration-300">
                <div className="absolute -right-6 -bottom-6 opacity-5 group-hover:opacity-10 transition-opacity transform group-hover:scale-110 duration-500">
                  <DollarSign size={120} className="text-[var(--accent-teal)]" />
                </div>
                <p className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">Median Salary</p>
                <div className="flex items-baseline gap-2 mb-4">
                  <span className="text-4xl font-black text-[var(--accent-teal)]">
                    <AnimatedCounter value={demandData.salary_range.median} prefix={demandData.salary_currency === 'INR' ? '₹' : '$'} />
                  </span>
                </div>
                {/* Visual Slider */}
                <div className="relative h-2 w-full bg-[var(--bg-deep)] rounded-full mt-6 mb-2">
                  <div className="absolute inset-y-0 bg-gradient-to-r from-[var(--bg-elevated)] via-[var(--accent-teal)] to-[var(--bg-elevated)] opacity-60 rounded-full" 
                       style={{ left: '10%', right: '10%' }}></div>
                  {/* Min marker */}
                  <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-[var(--bg-surface)] border-2 border-[var(--text-muted)] shadow z-10" style={{ left: '10%' }}></div>
                  <span className="absolute -bottom-5 left-[10%] -translate-x-1/2 text-[10px] text-[var(--text-muted)] font-medium">
                    {formatCurrency(demandData.salary_range.min, demandData.salary_currency)}
                  </span>
                  {/* Median marker */}
                  <div className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-[var(--accent-teal)] shadow-[0_0_10px_var(--accent-teal)] z-20" style={{ left: '50%', transform: 'translate(-50%, -50%)' }}></div>
                  <span className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs text-[var(--accent-teal)] font-bold">
                    Median
                  </span>
                  {/* Max marker */}
                  <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-[var(--bg-surface)] border-2 border-[var(--text-muted)] shadow z-10" style={{ left: '90%' }}></div>
                  <span className="absolute -bottom-5 left-[90%] -translate-x-1/2 text-[10px] text-[var(--text-muted)] font-medium">
                    {formatCurrency(demandData.salary_range.max, demandData.salary_currency)}
                  </span>
                </div>
              </motion.div>

              {/* Total Postings */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl relative overflow-hidden group hover:-translate-y-1 transition-transform duration-300">
                <div className="absolute -right-6 -bottom-6 opacity-5 group-hover:opacity-10 transition-opacity transform group-hover:scale-110 duration-500">
                  <Users size={120} className="text-[var(--accent-warm)]" />
                </div>
                <p className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">Active Jobs</p>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-5xl font-black text-[var(--text-primary)]">
                    <AnimatedCounter value={demandData.total_postings} />
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <Briefcase size={14} /> Open positions right now
                </div>
              </motion.div>
            </div>

            {/* MIDDLE ROW: Charts & Skills */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              
              {/* Demand History Area Chart */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl h-[400px] flex flex-col relative">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                      <Activity size={18} className="text-[var(--accent-lavender)]" />
                      Demand History
                    </h3>
                    <p className="text-xs text-[var(--text-muted)] mt-1">6-month trend for {demandData.role}</p>
                  </div>
                </div>
                <div className="flex-1 w-full relative z-10">
                  <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                    <AreaChart data={historyData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="colorDemand" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="var(--accent-lavender)" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="var(--accent-lavender)" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-subtle)" opacity={0.4} />
                      <XAxis dataKey="date" tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short' })} axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} dy={10} />
                      <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                      <YAxis yAxisId="right" orientation="right" hide />
                      <RechartsTooltip content={<CustomAreaTooltip />} cursor={{ stroke: 'var(--border-subtle)', strokeWidth: 1, strokeDasharray: '4 4' }} />
                      <Area yAxisId="left" type="monotone" dataKey="demand" stroke="var(--accent-lavender)" strokeWidth={3} fillOpacity={1} fill="url(#colorDemand)" activeDot={{ r: 6, fill: 'var(--bg-surface)', stroke: 'var(--accent-lavender)', strokeWidth: 2 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>

              {/* Trending Skills Pills */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl h-[400px] flex flex-col">
                <div className="mb-6">
                  <h3 className="text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <TrendingUp size={18} className="text-[var(--accent-warm)]" />
                    Top Required Skills
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Ranked by frequency in current job postings.</p>
                </div>
                
                <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                  <div className="flex flex-wrap gap-2.5">
                    {demandData.trending_skills.map((skill, index) => {
                      const total = demandData.trending_skills.length;
                      const intensity = 1 - (index / total) * 0.7; // From 1.0 down to 0.3
                      const bgColor = `hsla(var(--accent-warm-hsl) / ${intensity * 0.2})`;
                      const borderColor = `hsla(var(--accent-warm-hsl) / ${intensity * 0.4})`;
                      const textColor = `hsla(var(--accent-warm-hsl) / ${0.7 + intensity * 0.3})`;
                      
                      return (
                        <motion.div 
                          key={skill}
                          initial={{ opacity: 0, scale: 0.9 }}
                          animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: index * 0.03, type: 'spring' }}
                          className="px-4 py-2.5 rounded-full border flex items-center gap-2 hover:-translate-y-0.5 transition-transform cursor-default"
                          style={{ backgroundColor: bgColor, borderColor: borderColor }}
                        >
                          <span className="text-[10px] font-bold opacity-60 w-4" style={{ color: textColor }}>#{index + 1}</span>
                          <span className="text-sm font-semibold" style={{ color: textColor }}>{skill}</span>
                        </motion.div>
                      );
                    })}
                  </div>
                </div>
              </motion.div>
            </div>

            {/* BOTTOM ROW: Benchmarking & Companies */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Peer Benchmarking Radar */}
              <motion.div variants={itemVars} className="lg:col-span-2 glass-card p-6 border border-[var(--border-subtle)] rounded-xl min-h-[450px] flex flex-col">
                <div className="mb-2">
                  <h3 className="text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <Users size={18} className="text-[var(--accent-teal)]" />
                    Peer Benchmarking
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Compare your skillset against the market average for top requirements.</p>
                </div>
                
                {benchmarkData?.insufficient_data ? (
                  <div className="flex-1 flex flex-col items-center justify-center text-center">
                    <div className="w-12 h-12 rounded-full bg-[var(--bg-elevated)] flex items-center justify-center mb-4">
                      <Star size={20} className="text-[var(--text-muted)]" />
                    </div>
                    <p className="text-sm text-[var(--text-primary)] font-medium">Gathering Data</p>
                    <p className="text-xs text-[var(--text-muted)] mt-1 max-w-xs">{benchmarkData.message}</p>
                  </div>
                ) : radarData.length > 0 ? (
                  <div className="flex flex-col md:flex-row flex-1 gap-6 mt-4">
                    <div className="w-full md:w-1/2 h-[300px]">
                      <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                        <RadarChart cx="50%" cy="50%" outerRadius="65%" data={radarData}>
                          <PolarGrid stroke="var(--border-subtle)" strokeDasharray="3 3" />
                          <PolarAngleAxis dataKey="skill" tick={{ fill: 'var(--text-secondary)', fontSize: 11, fontWeight: 500 }} />
                          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                          <Radar name="Market Avg" dataKey="Market Avg" stroke="var(--accent-lavender)" fill="var(--accent-lavender)" fillOpacity={0.2} strokeWidth={2} isAnimationActive={true} />
                          <Radar name="You" dataKey="You" stroke="var(--accent-teal)" fill="var(--accent-teal)" fillOpacity={0.5} strokeWidth={2} isAnimationActive={true} />
                          <RechartsTooltip contentStyle={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)', borderRadius: '8px' }} itemStyle={{ fontSize: '12px' }} />
                        </RadarChart>
                      </ResponsiveContainer>
                      <div className="flex items-center justify-center gap-6 mt-2">
                        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]"><span className="w-3 h-3 rounded bg-[var(--accent-lavender)]/50 border border-[var(--accent-lavender)]"></span> Market</div>
                        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]"><span className="w-3 h-3 rounded bg-[var(--accent-teal)] border border-[var(--accent-teal)]"></span> You</div>
                      </div>
                    </div>
                    
                    {/* User's Skills List next to Radar */}
                    <div className="w-full md:w-1/2 flex flex-col justify-center">
                      <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-4 pb-2 border-b border-[var(--border-subtle)]">Your Benchmark Gaps</h4>
                      {missingSkills.length > 0 ? (
                        <ul className="space-y-3">
                          {missingSkills.slice(0, 5).map((skill, idx) => (
                            <motion.li key={idx} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + idx * 0.1 }} className="flex items-start gap-2.5">
                              <XCircle size={16} className="text-[var(--accent-coral)] shrink-0 mt-0.5" />
                              <div>
                                <p className="text-sm font-medium text-[var(--text-secondary)]">{skill}</p>
                                <p className="text-[10px] text-[var(--text-muted)]">High market demand</p>
                              </div>
                            </motion.li>
                          ))}
                        </ul>
                      ) : (
                        <div className="flex items-center gap-3 p-4 rounded-xl bg-[var(--accent-teal-dim)] border border-[var(--accent-teal)]/20">
                          <CheckCircle2 className="text-[var(--accent-teal)]" size={24} />
                          <p className="text-sm text-[var(--text-primary)] font-medium">You have all the top benchmarked skills!</p>
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <p className="py-12 text-center text-sm text-[var(--text-muted)] m-auto">Analyze a resume to view benchmarking.</p>
                )}
              </motion.div>

              {/* Top Companies */}
              <motion.div variants={itemVars} className="glass-card p-6 border border-[var(--border-subtle)] rounded-xl min-h-[450px] flex flex-col">
                <div className="mb-6">
                  <h3 className="text-lg font-bold text-[var(--text-primary)] flex items-center gap-2">
                    <Building2 size={18} className="text-[var(--accent-warm)]" />
                    Top Hiring Companies
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Actively recruiting for this role.</p>
                </div>
                
                <div className="flex-1 flex flex-col justify-between">
                  {companiesData?.companies && companiesData.companies.length > 0 ? (
                    <div className="space-y-4">
                      {companiesData.companies.map((company, idx) => {
                        const hasLogoUrl = Boolean(company.logo_url);
                        return (
                          <div key={idx} className="flex items-center justify-between p-3 rounded-lg hover:bg-[var(--bg-elevated)] transition-colors border border-transparent hover:border-[var(--border-subtle)]">
                            <div className="flex items-center gap-3">
                              {hasLogoUrl ? (
                                <img 
                                  src={company.logo_url} 
                                  alt={company.name} 
                                  className="w-8 h-8 rounded bg-white p-0.5 object-contain"
                                  onError={(e) => {
                                    e.target.onerror = null; 
                                    e.target.style.display = 'none';
                                    e.target.nextSibling.style.display = 'flex';
                                  }}
                                />
                              ) : null}
                              <div className="w-8 h-8 rounded bg-[var(--bg-deep)] flex items-center justify-center border border-[var(--border-subtle)]" style={{ display: hasLogoUrl ? 'none' : 'flex' }}>
                                <Building2 size={14} className="text-[var(--text-muted)]" />
                              </div>
                              <span className="font-medium text-sm text-[var(--text-primary)]">{company.name}</span>
                            </div>
                            {company.job_count && (
                              <span className="text-[10px] font-bold px-2 py-1 bg-[var(--accent-warm-dim)] text-[var(--accent-warm)] rounded-md">
                                {company.job_count}+ jobs
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                     <p className="text-sm text-[var(--text-muted)] text-center my-auto">Company data updating...</p>
                  )}
                  
                  <button className="w-full mt-6 py-2.5 rounded-lg border border-[var(--border-subtle)] text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] transition-colors">
                    View All Opportunities
                  </button>
                </div>
              </motion.div>
            </div>

          </motion.div>
        )}
      </div>
      <Footer />
    </PageTransition>
  );
}
