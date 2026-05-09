import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, Send, User, Bot, Loader2 } from 'lucide-react';
import { secureFetch } from '../api/base';

export default function InterviewPanel({ analysisId, role, isOpen, onClose }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  // Initialize session when opened
  useEffect(() => {
    if (isOpen && !sessionId) {
      const startSession = async () => {
        setIsTyping(true);
        try {
          const response = await secureFetch('/api/v1/mock-interview/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ analysis_id: analysisId })
          });
          const data = await response.json();
          setSessionId(data.session_id);
          
          // Map backend history to UI message format
          const formattedHistory = data.history.map((msg, idx) => ({
            id: `msg-${idx}`,
            sender: msg.role === 'assistant' ? 'ai' : 'user',
            text: msg.content
          }));
          setMessages(formattedHistory);
        } catch (err) {
          console.error("Failed to start session:", err);
          setMessages([{
            id: 'error',
            sender: 'ai',
            text: "Failed to connect to the interview server. Please try again later.",
            isError: true
          }]);
        } finally {
          setIsTyping(false);
        }
      };
      startSession();
    }
  }, [isOpen, analysisId, sessionId]);

  // Clean up state when closed
  useEffect(() => {
    if (!isOpen) {
      setSessionId(null);
      setMessages([]);
      setInputValue("");
      setIsTyping(false);
    }
  }, [isOpen]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = async () => {
    if (!inputValue.trim() || !sessionId) return;

    const userText = inputValue.trim();
    // Optimistically add user message
    setMessages(prev => [...prev, { id: `local-${Date.now()}`, sender: 'user', text: userText }]);
    setInputValue("");
    setIsTyping(true);

    try {
      const response = await secureFetch(`/api/v1/mock-interview/${sessionId}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userText })
      });
      
      const data = await response.json();
      
      // Update with authoritative history
      const formattedHistory = data.history.map((msg, idx) => ({
        id: `msg-${idx}`,
        sender: msg.role === 'assistant' ? 'ai' : 'user',
        text: msg.content
      }));
      setMessages(formattedHistory);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        sender: 'ai',
        text: "I'm having trouble connecting right now. Could you resend that?",
        isError: true
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      {/* Backdrop */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="relative w-full max-w-3xl h-[85vh] sm:h-[80vh] flex flex-col glass-card border border-[var(--border-subtle)] shadow-2xl overflow-hidden bg-[var(--bg-deep)]/95"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]/50 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--accent-lavender)]/20">
              <Bot className="text-[var(--accent-lavender)]" size={20} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Mock Interview</h2>
              <p className="text-xs text-[var(--text-muted)]">
                Role: {role}
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="p-2 rounded-full hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-custom">
          {messages.map((msg) => (
            <motion.div 
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-4 max-w-[85%] ${msg.sender === 'user' ? 'ml-auto flex-row-reverse' : ''}`}
            >
              {/* Avatar */}
              <div className="shrink-0 mt-auto">
                {msg.sender === 'ai' ? (
                  <div className="w-8 h-8 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--accent-lavender)]/20 shadow-sm">
                    <Bot className="text-[var(--accent-lavender)]" size={16} />
                  </div>
                ) : (
                  <div className="w-8 h-8 rounded-full bg-[var(--accent-warm-dim)] flex items-center justify-center border border-[var(--accent-warm)]/20 shadow-sm">
                    <User className="text-[var(--accent-warm)]" size={16} />
                  </div>
                )}
              </div>

              {/* Bubble */}
              <div className={`flex flex-col gap-1 ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
                  ${msg.sender === 'user' 
                    ? 'bg-[var(--accent-warm)] text-[#fff] rounded-br-sm' 
                    : msg.isError
                      ? 'bg-[var(--accent-coral-dim)] border border-[var(--accent-coral)]/30 text-[var(--text-primary)] rounded-bl-sm'
                      : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] rounded-bl-sm'
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            </motion.div>
          ))}
          
          {isTyping && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4 max-w-[85%]">
              <div className="shrink-0 mt-auto">
                <div className="w-8 h-8 rounded-full bg-[var(--accent-lavender-dim)] flex items-center justify-center border border-[var(--accent-lavender)]/20 shadow-sm">
                  <Bot className="text-[var(--accent-lavender)]" size={16} />
                </div>
              </div>
              <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-[var(--bg-elevated)] border border-[var(--border-subtle)] flex items-center gap-1 h-[44px]">
                <span className="typing-dot"></span>
                <span className="typing-dot" style={{ animationDelay: '0.2s' }}></span>
                <span className="typing-dot" style={{ animationDelay: '0.4s' }}></span>
              </div>
            </motion.div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]/80 backdrop-blur-md">
          <div className="relative flex items-end gap-2 max-w-4xl mx-auto">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Type your answer here... (Shift+Enter for new line)"
              className="flex-1 max-h-32 min-h-[52px] bg-[var(--bg-deep)] border border-[var(--border-subtle)] rounded-2xl py-3 px-4 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-lavender)] focus:ring-1 focus:ring-[var(--accent-lavender)] resize-none scrollbar-custom"
              disabled={isTyping || !sessionId}
            />
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || isTyping || !sessionId}
              className="h-[52px] w-[52px] shrink-0 rounded-full bg-[var(--accent-lavender)] hover:bg-[var(--accent-lavender)]/90 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 cursor-pointer"
            >
              <Send size={20} className="ml-1" />
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
