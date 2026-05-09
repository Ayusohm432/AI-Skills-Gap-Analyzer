import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar, Cell, Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis } from 'recharts';
import { TrendingUp, Users, DollarSign, Activity, Briefcase, ChevronDown, Loader2, AlertCircle } from 'lucide-react';
import { secureFetch } from '../api/base';
import PageTransition from '../components/PageTransition';
import Navbar from '../components/Navbar';
import Footer from '../components/Footer';

// Format currency
const formatCurrency = (value, currency = 'INR') => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: currency,
    maximumFractionDigits: 0,
  }).format(value);
};

// Custom Tooltip for Line Chart
const CustomLineTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-card border border-[var(--border-subtle)] p-3 shadow-xl text-sm">
        <p className="text-[var(--text-muted)] mb-2 font-medium">{new Date(label).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</p>
        <p className="text-[var(--text-primary)] font-semibold flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[var(--accent-lavender)]"></div>
          Demand Score: {payload[0].value}
        </p>
        <p className="text-[var(--text-primary)] font-semibold flex items-center gap-2 mt-1">
          <div className="w-2 h-2 rounded-full bg-[var(--accent-teal)]"></div>
          Job Postings: {payload[1].value.toLocaleString()}
        </p>
      </div>
    );
  }
  return null;
};

// Custom Tooltip for Bar Chart
const CustomBarTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-card border border-[var(--border-subtle)] p-3 shadow-xl text-sm">
        <p className="text-[var(--text-primary)] font-semibold">{label}</p>
        <p className="text-[var(--text-muted)] mt-1">Demand Rank: <span className="text-[var(--accent-warm)]">#{payload[0].value}</span></p>
      </div>
    );
  }
  return null;
};

// Custom Tooltip for Radar Chart
const CustomRadarTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-card border border-[var(--border-subtle)] p-3 shadow-xl text-sm min-w-[150px]">
        <p className="text-[var(--text-primary)] font-semibold mb-2">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="text-[var(--text-muted)] flex items-center justify-between gap-4">
            <span className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }}></div>
              {entry.name}:
            </span>
            <span className="font-semibold text-[var(--text-primary)]">{entry.value}%</span>
          </p>
        ))}
      </div>
    );
  }
  return null;
};


export default function MarketPage() {
  const [roles, setRoles] = useState([]);
  const [selectedRole, setSelectedRole] = useState('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  
  const [demandData, setDemandData] = useState(null);
  const [benchmarkData, setBenchmarkData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch roles list on mount
  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const res = await secureFetch('/api/v1/market/roles');
        if (!res.ok) throw new Error('Failed to fetch roles');
        const data = await res.json();
        setRoles(data.roles);
        
        // Default to first role (or user's saved role if exists)
        const savedRole = localStorage.getItem("userSelectedRole");
        if (savedRole && data.roles.includes(savedRole)) {
            setSelectedRole(savedRole);
        } else if (data.roles.length > 0) {
            setSelectedRole(data.roles.find(r => r !== "Auto Detect") || data.roles[0]);
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchRoles();
  }, []);

  // Fetch market and benchmark data when role changes
  useEffect(() => {
    if (!selectedRole || selectedRole === "Auto Detect") return;

    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [demandRes, benchmarkRes] = await Promise.all([
          secureFetch(`/api/v1/market/demand?role=${encodeURIComponent(selectedRole)}`),
          secureFetch(`/api/v1/market/benchmarks?role=${encodeURIComponent(selectedRole)}`).catch(() => null)
        ]);

        if (!demandRes.ok) {
          throw new Error('Failed to fetch market demand');
        }

        const demand = await demandRes.json();
        setDemandData(demand);

        if (benchmarkRes && benchmarkRes.ok) {
          const bench = await benchmarkRes.json();
          setBenchmarkData(bench);
        } else {
          setBenchmarkData(null);
        }

      } catch (err) {
        console.error(err);
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [selectedRole]);


  // Prepare Bar Chart Data (Trending Skills)
  // We mock a frequency/rank based on index since the API just returns a list
  const trendingSkillsData = demandData?.trending_skills.map((skill, index) => ({
    name: skill,
    rank: demandData.trending_skills.length - index, // Inverse rank for bar height
  })) || [];

  // Prepare Line Chart Data (History)
  const historyData = [...(demandData?.history || [])].reverse().map(h => ({
    date: h.captured_at,
    demand: h.demand_score,
    postings: h.total_postings,
  }));

  // Prepare Radar Chart Data (Peer Benchmarking)
  // We combine top_skills and common_gaps to show the market landscape
  const radarData = [];
  if (benchmarkData && !benchmarkData.insufficient_data) {
      const topSkills = benchmarkData.top_skills || [];
      const userHas = benchmarkData.user_stats?.has_top_skills || [];
      
      topSkills.slice(0, 6).forEach(ts => {
          radarData.push({
              skill: ts.skill,
              "Market Avg": ts.freq_pct,
              "You": userHas.includes(ts.skill) ? 100 : 0
          });
      });
  }

  return (
    <PageTransition>
      <Navbar />
      
      <div className="min-h-screen pt-24 pb-20 px-6 lg:px-8 max-w-7xl mx-auto space-y-8">
        
        {/* Header & Role Selector */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-20">
          <div>
            <h1 className="text-3xl font-bold text-[var(--text-primary)]">Market Intelligence</h1>
            <p className="text-[var(--text-muted)] mt-2">Live demand, salary trends, and peer benchmarking.</p>
          </div>
          
          <div className="relative min-w-[240px]">
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] hover:border-[var(--accent-lavender)] transition-all shadow-sm"
            >
              <div className="flex items-center gap-2">
                <Briefcase size={16} className="text-[var(--accent-lavender)]" />
                <span className="font-medium text-sm">{selectedRole || 'Select a Role'}</span>
              </div>
              <ChevronDown size={16} className={`text-[var(--text-muted)] transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            
            <AnimatePresence>
              {isDropdownOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="absolute top-full mt-2 w-full glass-card border border-[var(--border-subtle)] shadow-2xl rounded-xl overflow-hidden py-2 max-h-60 overflow-y-auto z-50 scrollbar-custom"
                >
                  {roles.filter(r => r !== 'Auto Detect').map(role => (
                    <button
                      key={role}
                      onClick={() => {
                        setSelectedRole(role);
                        setIsDropdownOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                        role === selectedRole 
                          ? 'bg-[var(--accent-lavender-dim)] text-[var(--accent-lavender)] font-medium' 
                          : 'text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      {role}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="min-h-[50vh] flex items-center justify-center">
             <Loader2 className="animate-spin text-[var(--accent-warm)]" size={40} />
          </div>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <div className="min-h-[50vh] flex items-center justify-center">
             <div className="glass-card border border-[var(--accent-coral)]/30 p-8 flex flex-col items-center text-center max-w-md">
                <AlertCircle className="text-[var(--accent-coral)] mb-4" size={48} />
                <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">Data Unavailable</h3>
                <p className="text-sm text-[var(--text-muted)]">{error}</p>
             </div>
          </div>
        )}

        {/* Dashboard Content */}
        {!isLoading && !error && demandData && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-8"
          >
            {/* Top Metric Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              
              {/* Demand Score */}
              <div className="glass-card border border-[var(--border-subtle)] p-6 relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <Activity size={80} className="text-[var(--accent-lavender)]" />
                </div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center">
                    <Activity size={20} className="text-[var(--accent-lavender)]" />
                  </div>
                  <h3 className="text-[var(--text-muted)] font-medium">Market Demand</h3>
                </div>
                <div className="flex items-end gap-3">
                  <span className="text-4xl font-bold text-[var(--text-primary)]">{demandData.demand_score}/100</span>
                  <span className={`text-sm font-medium mb-1 px-2 py-0.5 rounded-full ${
                    demandData.trend === 'rising' ? 'bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]' :
                    demandData.trend === 'declining' ? 'bg-[var(--accent-coral-dim)] text-[var(--accent-coral)]' :
                    'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
                  }`}>
                    {demandData.trend === 'rising' ? '↑' : demandData.trend === 'declining' ? '↓' : '→'} {Math.abs(demandData.yoy_growth_pct)}% YoY
                  </span>
                </div>
              </div>

              {/* Salary Range */}
              <div className="glass-card border border-[var(--border-subtle)] p-6 relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <DollarSign size={80} className="text-[var(--accent-teal)]" />
                </div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-[var(--accent-teal-dim)] flex items-center justify-center">
                    <DollarSign size={20} className="text-[var(--accent-teal)]" />
                  </div>
                  <h3 className="text-[var(--text-muted)] font-medium">Median Salary</h3>
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-3xl font-bold text-[var(--text-primary)]">
                    {formatCurrency(demandData.salary_range.median, demandData.salary_currency)}
                  </span>
                  <span className="text-xs text-[var(--text-muted)] font-medium">
                    Range: {formatCurrency(demandData.salary_range.min, demandData.salary_currency)} - {formatCurrency(demandData.salary_range.max, demandData.salary_currency)}
                  </span>
                </div>
              </div>

              {/* Total Postings */}
              <div className="glass-card border border-[var(--border-subtle)] p-6 relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                  <Users size={80} className="text-[var(--accent-warm)]" />
                </div>
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-[var(--accent-warm-dim)] flex items-center justify-center">
                    <Users size={20} className="text-[var(--accent-warm)]" />
                  </div>
                  <h3 className="text-[var(--text-muted)] font-medium">Active Jobs</h3>
                </div>
                <div className="flex items-end gap-3">
                  <span className="text-4xl font-bold text-[var(--text-primary)]">{demandData.total_postings.toLocaleString()}</span>
                  <span className="text-xs text-[var(--text-muted)] mb-1.5 uppercase tracking-wider font-semibold">Live Postings</span>
                </div>
              </div>

            </div>

            {/* Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              
              {/* Trending Skills Bar Chart */}
              <div className="glass-card border border-[var(--border-subtle)] p-6 flex flex-col h-[400px]">
                <div className="mb-6">
                  <h3 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
                    <TrendingUp size={18} className="text-[var(--accent-warm)]" />
                    Top Trending Skills
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Most frequently requested skills in active job descriptions.</p>
                </div>
                <div className="flex-1 w-full h-full min-h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trendingSkillsData} layout="vertical" margin={{ top: 0, right: 30, left: 40, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="var(--border-subtle)" opacity={0.5} />
                      <XAxis type="number" hide />
                      <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} width={90} />
                      <RechartsTooltip cursor={{ fill: 'var(--bg-elevated)' }} content={<CustomBarTooltip />} />
                      <Bar dataKey="rank" radius={[0, 4, 4, 0]} barSize={16}>
                        {trendingSkillsData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={`hsl(var(--accent-warm-hsl) / ${1 - (index * 0.08)})`} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Demand History Line Chart */}
              <div className="glass-card border border-[var(--border-subtle)] p-6 flex flex-col h-[400px]">
                <div className="mb-6">
                  <h3 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
                    <Activity size={18} className="text-[var(--accent-lavender)]" />
                    Demand History (6 Months)
                  </h3>
                  <p className="text-xs text-[var(--text-muted)] mt-1">Market demand score and active job postings over time.</p>
                </div>
                <div className="flex-1 w-full h-full min-h-[250px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={historyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-subtle)" opacity={0.5} />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short' })}
                        axisLine={false} 
                        tickLine={false} 
                        tick={{ fill: 'var(--text-muted)', fontSize: 12 }} 
                        dy={10}
                      />
                      <YAxis yAxisId="left" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                      <YAxis yAxisId="right" orientation="right" hide />
                      <RechartsTooltip content={<CustomLineTooltip />} />
                      <Line yAxisId="left" type="monotone" dataKey="demand" stroke="var(--accent-lavender)" strokeWidth={3} dot={{ fill: 'var(--bg-deep)', strokeWidth: 2, r: 4 }} activeDot={{ r: 6, fill: 'var(--accent-lavender)', stroke: 'var(--bg-deep)' }} />
                      <Line yAxisId="right" type="monotone" dataKey="postings" stroke="var(--accent-teal)" strokeWidth={2} strokeDasharray="5 5" dot={false} activeDot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

            </div>

            {/* Peer Benchmarking Radar */}
            <div className="glass-card border border-[var(--border-subtle)] p-6 flex flex-col items-center">
              <div className="w-full mb-6">
                <h3 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
                  <Users size={18} className="text-[var(--accent-teal)]" />
                  Peer Benchmarking
                </h3>
                <p className="text-xs text-[var(--text-muted)] mt-1">Compare your skills against the most common skills found in other users targeting this role.</p>
              </div>
              
              {benchmarkData?.insufficient_data ? (
                <div className="py-12 text-center max-w-sm">
                  <div className="w-12 h-12 rounded-full bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center justify-center mx-auto mb-4">
                    <Users size={20} className="text-[var(--text-muted)]" />
                  </div>
                  <h4 className="text-sm font-medium text-[var(--text-primary)] mb-1">Building Benchmark Data</h4>
                  <p className="text-xs text-[var(--text-muted)]">{benchmarkData.message}</p>
                </div>
              ) : radarData.length > 0 ? (
                <div className="w-full h-[350px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                      <PolarGrid stroke="var(--border-subtle)" />
                      <PolarAngleAxis dataKey="skill" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                      <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                      <Radar name="Market Avg" dataKey="Market Avg" stroke="var(--accent-lavender)" fill="var(--accent-lavender)" fillOpacity={0.3} />
                      <Radar name="You" dataKey="You" stroke="var(--accent-teal)" fill="var(--accent-teal)" fillOpacity={0.5} />
                      <RechartsTooltip content={<CustomRadarTooltip />} />
                    </RadarChart>
                  </ResponsiveContainer>
                  
                  {/* Custom Legend */}
                  <div className="flex items-center justify-center gap-6 mt-4">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded bg-[var(--accent-lavender)] opacity-70"></div>
                      <span className="text-xs font-medium text-[var(--text-muted)]">Market Average</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded bg-[var(--accent-teal)]"></div>
                      <span className="text-xs font-medium text-[var(--text-muted)]">Your Proficiency</span>
                    </div>
                  </div>
                </div>
              ) : (
                 <p className="py-12 text-sm text-[var(--text-muted)]">Please complete a resume analysis to see your personal benchmarking.</p>
              )}
            </div>

          </motion.div>
        )}
      </div>
      <Footer />
    </PageTransition>
  );
}
