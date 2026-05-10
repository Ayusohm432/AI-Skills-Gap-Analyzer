import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  X, Send, User, Bot, Loader2, Mic, ThumbsUp, ThumbsDown,
  ChevronRight, Sparkles, Clock, BarChart2, CheckCircle2, AlertCircle, RotateCcw
} from 'lucide-react';
import { secureFetch } from '../api/base';

// ─── Typing Dots ───────────────────────────────────────────────────
function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 0.2, 0.4].map((delay, i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-[var(--accent-lavender)]"
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.1, 0.8] }}
          transition={{ duration: 1.2, repeat: Infinity, delay, ease: 'easeInOut' }}
        />
      ))}
    </div>
  );
}

// ─── Message Bubble ────────────────────────────────────────────────
function MessageBubble({ msg, onFeedback }) {
  const isAI = msg.sender === 'ai';
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 320, damping: 24 }}
      className={`flex gap-3 ${isAI ? '' : 'flex-row-reverse'}`}
    >
      {/* Avatar */}
      <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-sm border
        ${isAI
          ? 'bg-[var(--accent-lavender-dim)] border-[var(--accent-lavender-dim)]'
          : 'bg-[var(--accent-warm-dim)] border-[var(--accent-warm-dim)]'
        }`}
      >
        {isAI
          ? <Bot size={15} className="text-[var(--accent-lavender)]" />
          : <User size={15} className="text-[var(--accent-warm)]" />
        }
      </div>

      {/* Content */}
      <div className={`flex flex-col gap-1.5 max-w-[80%] ${isAI ? 'items-start' : 'items-end'}`}>
        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
          ${isAI
            ? msg.isError
              ? 'bg-[var(--accent-coral-dim)] border border-[var(--accent-coral-dim)] text-[var(--text-primary)] rounded-tl-sm'
              : msg.isSystem
                ? 'bg-[var(--bg-elevated)] border border-[var(--border-hover)] text-[var(--accent-lavender)] rounded-tl-sm font-medium'
                : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] rounded-tl-sm'
            : 'bg-[var(--accent-warm)] text-white rounded-tr-sm'
          }`}
        >
          {msg.isError && (
            <div className="flex items-center gap-2 mb-2 text-[var(--accent-coral)] text-xs font-semibold">
              <AlertCircle size={12} /> Connection Error
            </div>
          )}
          {msg.text}
        </div>

        {/* AI message feedback */}
        {isAI && !msg.isError && !msg.isSystem && onFeedback && (
          <div className="flex items-center gap-1 px-1">
            <button
              onClick={() => onFeedback(msg.id, 'up')}
              className={`p-1 rounded transition-colors ${msg.feedback === 'up' ? 'text-[var(--accent-teal)]' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
              title="Helpful"
            >
              <ThumbsUp size={11} />
            </button>
            <button
              onClick={() => onFeedback(msg.id, 'down')}
              className={`p-1 rounded transition-colors ${msg.feedback === 'down' ? 'text-[var(--accent-coral)]' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
              title="Not helpful"
            >
              <ThumbsDown size={11} />
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Progress Bar ──────────────────────────────────────────────────
function InterviewProgress({ current, total, startTime }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [startTime]);

  const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
  const secs = (elapsed % 60).toString().padStart(2, '0');
  const pct = Math.min((current / total) * 100, 100);

  return (
    <div className="flex items-center gap-4 px-6 py-3 border-b border-[var(--border-subtle)] bg-[var(--bg-deep)]">
      {/* Step counter */}
      <div className="flex items-center gap-2 shrink-0">
        <BarChart2 size={12} className="text-[var(--text-muted)]" />
        <span className="text-xs font-semibold text-[var(--text-secondary)]">
          Q <span className="text-[var(--accent-lavender)]">{Math.min(current, total)}</span>
          <span className="text-[var(--text-muted)]">/{total}</span>
        </span>
      </div>

      {/* Progress bar */}
      <div className="flex-1 h-1.5 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
        <motion.div
          className="h-full bg-[var(--accent-lavender)] rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ type: 'spring', stiffness: 180, damping: 22 }}
          style={{ boxShadow: '0 0 8px var(--accent-lavender-dim)' }}
        />
      </div>

      {/* Timer */}
      <div className="flex items-center gap-1 shrink-0 text-xs text-[var(--text-muted)] font-mono">
        <Clock size={11} />
        {mins}:{secs}
      </div>
    </div>
  );
}

// ─── Question Preview Card (in sidebar / before entering) ──────────
function SuggestionPill({ text, onClick }) {
  return (
    <motion.button
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className="text-left text-xs text-[var(--text-secondary)] px-3 py-2 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] hover:border-[var(--accent-lavender-dim)] hover:text-[var(--text-primary)] transition-all w-full"
    >
      {text}
    </motion.button>
  );
}

// ─── Main Component ─────────────────────────────────────────────────
export default function InterviewPanel({ analysisId, role, isOpen, onClose }) {
  const [sessionId, setSessionId]     = useState(null);
  const [messages, setMessages]       = useState([]);
  const [inputValue, setInputValue]   = useState('');
  const [isTyping, setIsTyping]       = useState(false);
  const [questionCount, setQCount]    = useState(0);
  const [totalQuestions, setTotalQ]   = useState(5);
  const [startTime]                   = useState(Date.now());
  const [isDone, setIsDone]           = useState(false);
  const [error, setError]             = useState(null);
  const messagesEndRef                = useRef(null);
  const textareaRef                   = useRef(null);

  // ── Session init ──
  useEffect(() => {
    if (!isOpen || sessionId) return;

    const startSession = async () => {
      setIsTyping(true);
      setError(null);
      try {
        const res  = await secureFetch('/api/v1/mock-interview/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ analysis_id: analysisId }),
        });
        const data = await res.json();
        setSessionId(data.session_id);
        setTotalQ(data.total_questions || 5);

        const formatted = data.history.map((m, i) => ({
          id:       `init-${i}`,
          sender:   m.role === 'assistant' ? 'ai' : 'user',
          text:     m.content,
          isSystem: i === 0,
        }));
        setMessages(formatted);
        setQCount(1);
      } catch {
        setError('Could not connect to interview server. Please try again.');
      } finally {
        setIsTyping(false);
      }
    };
    startSession();
  }, [isOpen, analysisId, sessionId]);

  // ── Reset on close ──
  useEffect(() => {
    if (!isOpen) {
      setSessionId(null);
      setMessages([]);
      setInputValue('');
      setIsTyping(false);
      setIsDone(false);
      setQCount(0);
      setError(null);
    }
  }, [isOpen]);

  // ── Auto-scroll ──
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // ── Focus textarea ──
  useEffect(() => {
    if (isOpen && !isTyping) {
      setTimeout(() => textareaRef.current?.focus(), 100);
    }
  }, [isOpen, isTyping]);

  // ── Message feedback ──
  const handleFeedback = useCallback((id, type) => {
    setMessages(prev =>
      prev.map(m => m.id === id ? { ...m, feedback: m.feedback === type ? null : type } : m)
    );
  }, []);

  // ── Send message ──
  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || !sessionId || isTyping || isDone) return;

    const userMsg = { id: `u-${Date.now()}`, sender: 'user', text };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      const res  = await secureFetch(`/api/v1/mock-interview/${sessionId}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();

      const formatted = data.history.map((m, i) => ({
        id:     `msg-${i}`,
        sender: m.role === 'assistant' ? 'ai' : 'user',
        text:   m.content,
        isSystem: i === 0,
      }));
      setMessages(formatted);

      const nextQ = questionCount + 1;
      setQCount(nextQ);

      if (data.is_complete || nextQ > totalQuestions) {
        setIsDone(true);
      }
    } catch {
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`, sender: 'ai', text: "I'm having trouble connecting. Please resend your answer.", isError: true,
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Panel */}
      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 30, scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28 }}
        className="relative w-full sm:max-w-2xl h-[95vh] sm:h-[82vh] flex flex-col rounded-t-3xl sm:rounded-3xl overflow-hidden shadow-2xl border border-[var(--border-subtle)]"
        style={{ background: 'var(--bg-deep)' }}
      >
        {/* ── Header ── */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-[var(--border-subtle)]"
          style={{ background: 'linear-gradient(135deg, rgba(155,142,196,0.08) 0%, transparent 60%)' }}
        >
          {/* AI avatar with pulse ring */}
          <div className="relative shrink-0">
            <div className="w-10 h-10 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--accent-lavender-dim)]">
              <Bot size={20} className="text-[var(--accent-lavender)]" />
            </div>
            <motion.div
              className="absolute inset-0 rounded-full border border-[var(--accent-lavender)]"
              animate={{ scale: [1, 1.35, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
            />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-[var(--text-primary)]">AI Interviewer</h2>
              <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[var(--accent-teal-dim)] text-[var(--accent-teal)]">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent-teal)] animate-pulse" />
                Live
              </span>
            </div>
            <p className="text-xs text-[var(--text-muted)] truncate">
              <Sparkles size={10} className="inline mr-1 text-[var(--accent-lavender)]" />
              {role || 'Technical Interview'} · Deep Space AI
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Restart button */}
            <button
              onClick={() => { setSessionId(null); setMessages([]); setQCount(0); setIsDone(false); }}
              className="p-2 rounded-xl hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              title="Restart interview"
            >
              <RotateCcw size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ── Progress bar ── */}
        {questionCount > 0 && !isDone && (
          <InterviewProgress
            current={questionCount}
            total={totalQuestions}
            startTime={startTime}
          />
        )}

        {/* ── Error banner ── */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="px-5 py-3 bg-[var(--accent-coral-dim)] border-b border-[var(--accent-coral-dim)] flex items-center gap-2 text-xs text-[var(--accent-coral)] font-medium"
            >
              <AlertCircle size={13} />
              {error}
              <button
                onClick={() => { setError(null); setSessionId(null); }}
                className="ml-auto underline cursor-pointer"
              >
                Retry
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Chat Area ── */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5 scrollbar-custom">
          {messages.length === 0 && !isTyping && !error && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center justify-center h-full gap-4 text-center py-8"
            >
              <div className="w-16 h-16 rounded-2xl bg-[var(--accent-lavender-dim)] flex items-center justify-center">
                <Bot size={30} className="text-[var(--accent-lavender)]" />
              </div>
              <div>
                <p className="text-sm font-semibold text-[var(--text-primary)] mb-1">Connecting to interviewer…</p>
                <p className="text-xs text-[var(--text-muted)]">Preparing your personalised questions</p>
              </div>
              <TypingDots />
            </motion.div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} onFeedback={handleFeedback} />
          ))}

          {/* Typing indicator */}
          <AnimatePresence>
            {isTyping && (
              <motion.div
                key="typing"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                className="flex gap-3 items-end"
              >
                <div className="w-8 h-8 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--accent-lavender-dim)]">
                  <Bot size={15} className="text-[var(--accent-lavender)]" />
                </div>
                <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-[var(--bg-elevated)] border border-[var(--border-subtle)]">
                  <TypingDots />
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Completion card */}
          <AnimatePresence>
            {isDone && (
              <motion.div
                initial={{ opacity: 0, scale: 0.94 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: 'spring', stiffness: 260, damping: 22 }}
                className="mx-auto max-w-sm text-center p-6 rounded-2xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] mt-4"
              >
                <div className="w-14 h-14 rounded-2xl bg-[var(--accent-teal-dim)] flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 size={28} className="text-[var(--accent-teal)]" />
                </div>
                <h3 className="text-base font-bold text-[var(--text-primary)] mb-1">Interview Complete!</h3>
                <p className="text-xs text-[var(--text-muted)] leading-relaxed mb-5">
                  You've answered all {totalQuestions} questions. Review your responses above to identify areas for improvement.
                </p>
                <div className="flex gap-2 justify-center">
                  <button
                    onClick={() => { setSessionId(null); setMessages([]); setQCount(0); setIsDone(false); }}
                    className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-xl bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-all"
                  >
                    <RotateCcw size={13} /> Retry
                  </button>
                  <button
                    onClick={onClose}
                    className="flex items-center gap-1.5 text-xs font-semibold px-4 py-2 rounded-xl bg-[var(--accent-lavender)] text-white hover:opacity-90 transition-all"
                  >
                    Done <ChevronRight size={13} />
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>

        {/* ── Input Area ── */}
        <AnimatePresence>
          {!isDone && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="px-4 pb-4 pt-3 border-t border-[var(--border-subtle)]"
              style={{ background: 'linear-gradient(0deg, var(--bg-surface) 0%, var(--bg-deep) 100%)' }}
            >
              {/* Quick tip */}
              <div className="flex items-center gap-1.5 mb-2 text-[10px] text-[var(--text-muted)]">
                <Sparkles size={9} className="text-[var(--accent-lavender)]" />
                <span>Answer thoroughly — think out loud like a real interview</span>
                <span className="ml-auto font-mono opacity-60">↵ Send · Shift+↵ New line</span>
              </div>

              <div className="flex items-end gap-2">
                <div className="flex-1 relative">
                  <textarea
                    ref={textareaRef}
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={isTyping ? "Waiting for interviewer…" : "Type your answer here…"}
                    disabled={isTyping || !sessionId || isDone}
                    rows={1}
                    className="w-full max-h-36 min-h-[48px] resize-none bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-2xl py-3 px-4 pr-12 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-lavender)] transition-colors scrollbar-custom disabled:opacity-50"
                    style={{ lineHeight: '1.5' }}
                    onInput={(e) => {
                      e.target.style.height = 'auto';
                      e.target.style.height = Math.min(e.target.scrollHeight, 144) + 'px';
                    }}
                  />

                  {/* Character hint when long */}
                  {inputValue.length > 100 && (
                    <span className="absolute bottom-2 right-3 text-[10px] text-[var(--text-muted)]">
                      {inputValue.length}
                    </span>
                  )}
                </div>

                {/* Send button */}
                <motion.button
                  whileHover={!isTyping && inputValue.trim() ? { scale: 1.07 } : {}}
                  whileTap={!isTyping && inputValue.trim() ? { scale: 0.93 } : {}}
                  onClick={handleSend}
                  disabled={!inputValue.trim() || isTyping || !sessionId || isDone}
                  className="h-[48px] w-[48px] shrink-0 rounded-2xl bg-[var(--accent-lavender)] flex items-center justify-center shadow-lg transition-opacity disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                  style={{ boxShadow: '0 4px 16px var(--accent-lavender-dim)' }}
                >
                  {isTyping
                    ? <Loader2 size={18} className="text-white animate-spin" />
                    : <Send size={18} className="text-white ml-0.5" />
                  }
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
