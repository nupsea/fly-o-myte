/**
 * AI Planner view — agent-loop powered journey modeling.
 *
 * Flow:
 *   1. User types a query → /planner/chat → reasoning shown as chat bubble + intent card
 *   2. If LLM needs info → chat bubble appears, user replies inline
 *   3. Intent card: Scout Now (→ Smart Scout), Refine (inline delta input)
 *   4. Sessions saved to localStorage as "Recent" history
 */
import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles,
  Plane,
  Search,
  RefreshCcw,
  RotateCcw,
  AlertCircle,
  Pencil,
  History,
  Trash2,
  FolderOpen,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'

// ── History ──────────────────────────────────────────────────────────────────

const HISTORY_KEY = 'fom_planner_history';

interface PlannerSession {
  id: string;
  timestamp: string;
  firstQuery: string;
  destination_iata: string;
  destination_display: string;
  origin_iata: string;
  nights: number;
  period: string;
  intent: any;        // full intent — needed to restore the intent card
  scoutParams: any;
}

function loadHistory(): PlannerSession[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}

function saveSession(intent: any, scoutParams: any, firstQuery: string): PlannerSession[] {
  const period = intent.month && intent.year
    ? new Date(intent.year, intent.month - 1).toLocaleString('en-AU', { month: 'short', year: 'numeric' })
    : intent.depart_earliest || '';
  // Dedup key: always month+year granularity so exact-date and month-mode plans for the
  // same destination+month don't create two separate history entries.
  const dedupMonth = intent.month && intent.year
    ? `${intent.year}-${String(intent.month).padStart(2, '0')}`
    : intent.depart_earliest
      ? intent.depart_earliest.slice(0, 7)   // "2027-04-02" → "2027-04"
      : period.replace(/\s/g, '-');
  const entry: PlannerSession = {
    id: `${intent.destination_iata}-${dedupMonth}`,
    timestamp: new Date().toISOString(),
    firstQuery,
    destination_iata: intent.destination_iata,
    destination_display: intent.destination_display,
    origin_iata: intent.origin_iata,
    nights: intent.nights,
    period,
    intent,           // full intent saved for restoration
    scoutParams,
  };
  // Upsert by id (same destination+period refreshes rather than duplicates)
  const updated = [entry, ...loadHistory().filter(s => s.id !== entry.id)].slice(0, 20);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
  return updated;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message { role: string; content: string }
interface DisplayMsg { role: 'user' | 'assistant'; content: string }

// ── Component ─────────────────────────────────────────────────────────────────

const Planner = () => {
  const navigate = useNavigate();

  // Conversation state
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [displayMsgs, setDisplayMsgs] = useState<DisplayMsg[]>([]);

  // Planner state
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<any>(null);
  const [scoutParams, setScoutParams] = useState<any>(null);

  // Refinement state
  const [refining, setRefining] = useState(false);
  const [refineInput, setRefineInput] = useState('');

  // History
  const [history, setHistory] = useState<PlannerSession[]>(loadHistory);

  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const refineRef = useRef<HTMLInputElement>(null);

  // Track the first user message for history labelling
  const firstQueryRef = useRef('');

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMsgs, intent]);

  useEffect(() => {
    if (refining) refineRef.current?.focus();
  }, [refining]);

  // ── Core call ──────────────────────────────────────────────────────────────

  const callPlanner = async (outgoingMessages: Message[]) => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch('/api/planner/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: outgoingMessages }),
      });

      let data: any;
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        data = await res.json();
      } else {
        const text = await res.text();
        throw new Error(text.slice(0, 120) || `HTTP ${res.status}`);
      }

      if (data.type === 'error') {
        setError(data.content || 'Planning failed');
      } else if (data.type === 'message') {
        setMessages(data.messages || outgoingMessages);
        setDisplayMsgs(prev => [...prev, { role: 'assistant', content: data.content }]);
      } else if (data.type === 'plan') {
        const reasoning: string | undefined = data.intent?.reasoning;
        const finalMessages = data.messages || outgoingMessages;
        if (reasoning) {
          setDisplayMsgs(prev => [...prev, { role: 'assistant', content: reasoning }]);
          setMessages([...finalMessages, { role: 'assistant', content: reasoning }]);
        } else {
          setMessages(finalMessages);
        }
        setIntent(data.intent);
        setScoutParams(data.scout_params);
        setRefining(false);
        setRefineInput('');
        // Save to history
        const updated = saveSession(data.intent, data.scout_params, firstQueryRef.current);
        setHistory(updated);
      }
    } catch (err: any) {
      setError(err.message || 'Network error');
    }
    setLoading(false);
  };

  // ── First query ────────────────────────────────────────────────────────────

  const handlePlan = async () => {
    if (!input.trim() || loading) return;
    const userText = input.trim();
    setInput('');
    if (!firstQueryRef.current) firstQueryRef.current = userText;
    const updated = [...messages, { role: 'user', content: userText }];
    setMessages(updated);
    setDisplayMsgs(prev => [...prev, { role: 'user', content: userText }]);
    await callPlanner(updated);
  };

  // ── Refinement ─────────────────────────────────────────────────────────────

  const handleRefine = async () => {
    if (!refineInput.trim() || loading) return;
    const userText = refineInput.trim();
    setRefineInput('');
    setRefining(false);
    setIntent(null);

    // Inject the current plan as an explicit assistant message so the LLM knows
    // exactly what it's refining. Without this, year/nights/origin can reset to
    // defaults when the user only mentions one field (e.g. "change the city").
    const base = intent
      ? [
          ...messages,
          {
            role: 'assistant',
            content:
              `Current plan: ${intent.destination_display} (${intent.destination_iata}), ` +
              (intent.depart_earliest
                ? `departing ${intent.depart_earliest}`
                : `${intent.month}/${intent.year}`) +
              `, ${intent.nights} nights, from ${intent.origin_iata}.`,
          },
        ]
      : messages;

    const updated = [...base, { role: 'user', content: userText }];
    setMessages(updated);
    setDisplayMsgs(prev => [...prev, { role: 'user', content: userText }]);
    await callPlanner(updated);
  };

  // ── Load session from history ──────────────────────────────────────────────

  const handleLoadSession = (s: PlannerSession) => {
    setIntent(s.intent);
    setScoutParams(s.scoutParams);
    setMessages([{ role: 'user', content: s.firstQuery }]);
    setDisplayMsgs([
      { role: 'user', content: s.firstQuery },
      ...(s.intent?.reasoning ? [{ role: 'assistant' as const, content: s.intent.reasoning }] : []),
    ]);
    firstQueryRef.current = s.firstQuery;
    setRefining(false);
    setError(null);
  };

  // ── Delete session from history ────────────────────────────────────────────

  const handleDeleteSession = (id: string) => {
    const updated = history.filter(s => s.id !== id);
    setHistory(updated);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
  };

  // ── Scout → navigate to Smart Scout ───────────────────────────────────────

  const handleScout = () => {
    if (!scoutParams || !intent) return;
    const hint = `${intent.destination_iata} — ${intent.destination_display}${intent.period ? ' · ' + intent.period : ''}`;
    navigate('/scout', { state: { scoutParams, plannerHint: hint } });
  };

  // ── Reset ──────────────────────────────────────────────────────────────────

  const handleNewSearch = () => {
    setInput('');
    setMessages([]);
    setDisplayMsgs([]);
    setIntent(null);
    setScoutParams(null);
    setRefining(false);
    setRefineInput('');
    setError(null);
    firstQueryRef.current = '';
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  const confidenceClass = (c: number) => c >= 0.8 ? 'green' : c >= 0.6 ? 'amber' : 'red';

  const intentSummary = () => {
    if (!intent) return '';
    const parts = [intent.destination_iata];
    if (intent.month && intent.year)
      parts.push(new Date(intent.year, intent.month - 1).toLocaleString('en-AU', { month: 'short', year: 'numeric' }));
    else if (intent.depart_earliest)
      parts.push(intent.depart_earliest);
    if (intent.nights) parts.push(`${intent.nights}n`);
    return parts.join(' · ');
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="view planner-view">
      <header className="view-header">
        <div className="header-content">
          <h1>AI Planner</h1>
          <p className="subtitle">Natural language journey modeling</p>
        </div>
        {(messages.length > 0 || intent) && (
          <div className="header-actions">
            <button className="btn btn-ghost btn-sm" onClick={handleNewSearch}>
              <RotateCcw size={14} /> New Search
            </button>
          </div>
        )}
      </header>

      <div className="planner-layout">
        {/* ── Left sidebar: persistent history ──────────────────────────── */}
        <aside className="planner-history-sidebar">
          <div className="history-heading">
            <History size={14} />
            <span>Recent</span>
          </div>
          {history.length === 0 ? (
            <p className="planner-history-empty">No recent searches yet.</p>
          ) : (
            <div className="history-list-sidebar">
              {history.map(s => (
                <div key={s.id} className="history-card glass">
                  <div className="history-card-top">
                    <span className="history-dest">{s.destination_iata}</span>
                    <button
                      className="btn-icon history-delete-btn"
                      onClick={() => handleDeleteSession(s.id)}
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                  <span className="history-detail">{s.destination_display}</span>
                  <div className="context-chips" style={{ marginTop: 6 }}>
                    {s.period && <span className="context-chip">{s.period}</span>}
                    <span className="context-chip">{s.nights}n</span>
                  </div>
                  <p className="history-query">"{s.firstQuery}"</p>
                  <div className="history-card-actions">
                    <span className="dim-text" style={{ fontSize: '0.68rem' }}>{relativeTime(s.timestamp)}</span>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        className="btn btn-light btn-sm"
                        onClick={() => handleLoadSession(s)}
                        title="Load and refine"
                      >
                        <FolderOpen size={11} /> Load
                      </button>
                      <button
                        className="btn btn-light btn-sm"
                        onClick={() => navigate('/scout', { state: { scoutParams: s.scoutParams, plannerHint: `${s.destination_iata} — ${s.destination_display}` } })}
                        title="Go to Scout with these params"
                      >
                        <Search size={11} /> Scout
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* ── Main content area ─────────────────────────────────────────── */}
        <div className="planner-main">
          {error && (
            <motion.div className="error-banner glass" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
              <AlertCircle size={18} />
              <span>{error}</span>
            </motion.div>
          )}

          {/* ── Idle state: centred omnibox ── */}
          {!intent && displayMsgs.length === 0 && !loading && (
            <div className="planner-container glass">
              <div className="omnibox">
                <Sparkles className="sparkle-icon" size={24} />
                <input
                  type="text"
                  placeholder="Where to? e.g. 'New Zealand in April for 10 days during school holidays'"
                  className="planner-input"
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handlePlan()}
                  disabled={loading}
                  autoFocus
                />
                <button className="btn btn-primary" onClick={handlePlan} disabled={loading || !input.trim()}>
                  <span>Plan</span>
                </button>
              </div>
            </div>
          )}

          {/* ── Active conversation: scrollable messages + sticky input bar ── */}
          {(displayMsgs.length > 0 || loading || intent) && (
            <div className="planner-chat-layout">
              {/* Scrollable messages area */}
              <div className="planner-chat-scroll">
                {loading && displayMsgs.length === 0 && (
                  <motion.div className="planner-loading glass" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <RefreshCcw className="animate-spin" size={28} style={{ color: 'var(--primary)' }} />
                    <span style={{ fontWeight: 600, color: 'var(--text-muted)' }}>Planning your trip...</span>
                  </motion.div>
                )}

                <AnimatePresence>
                  {displayMsgs.length > 0 && (
                    <motion.div className="planner-chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      {displayMsgs.map((msg, i) => (
                        <motion.div
                          key={i}
                          className={`chat-bubble ${msg.role}`}
                          initial={{ opacity: 0, y: 6 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.04 }}
                        >
                          {msg.role === 'assistant'
                            ? <div className="chat-md"><ReactMarkdown>{msg.content}</ReactMarkdown></div>
                            : msg.content}
                        </motion.div>
                      ))}
                      {loading && (
                        <div className="chat-bubble assistant loading-bubble">
                          <RefreshCcw className="animate-spin" size={14} />
                          <span>Thinking...</span>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                <div ref={chatEndRef} />
              </div>

              {/* Sticky input bar — shown while conversation is open and no intent card yet */}
              {!intent && (
                <div className="planner-input-bar glass">
                  <div className="omnibox">
                    <input
                      type="text"
                      placeholder="Reply or ask a follow-up..."
                      className="planner-input"
                      value={input}
                      onChange={e => setInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handlePlan()}
                      disabled={loading}
                      autoFocus
                    />
                    <button className="btn btn-primary" onClick={handlePlan} disabled={loading || !input.trim()}>
                      {loading ? <RefreshCcw className="animate-spin" size={16} /> : <span>Send</span>}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Intent Card */}
          <AnimatePresence>
            {intent && (
              <motion.div className="intent-card-v2 glass" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                <div className="intent-header-v2">
                  <div className="destination-badge">
                    <Plane size={20} />
                    <span>{intent.destination_iata} — {intent.destination_display}</span>
                  </div>
                </div>

                <div className="intent-details">
                  {intent.depart_earliest && intent.return_latest ? (
                    <div className="intent-date-range">{intent.depart_earliest} to {intent.return_latest}</div>
                  ) : intent.month && intent.year ? (
                    <div className="intent-date-range">
                      {new Date(intent.year, intent.month - 1).toLocaleString('en-AU', { month: 'long', year: 'numeric' })}
                    </div>
                  ) : null}
                  <div className="context-chips">
                    <span className="context-chip">{intent.nights} nights</span>
                    {intent.flex_days != null && <span className="context-chip">±{intent.flex_days} days flex</span>}
                    <span className="context-chip">from {intent.origin_iata}</span>
                  </div>
                </div>

                <div className="savings-meter">
                  <div className="meter-label">
                    <span>Confidence</span>
                    <span>{Math.round(intent.confidence * 100)}%</span>
                  </div>
                  <div className="meter-track">
                    <motion.div
                      className={`meter-fill ${confidenceClass(intent.confidence)}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.round(intent.confidence * 100)}%` }}
                      transition={{ duration: 0.7, ease: 'easeOut' }}
                    />
                  </div>
                </div>

                {intent.reasoning && <p className="intent-reasoning">{intent.reasoning}</p>}

                {/* Refinement input */}
                <AnimatePresence>
                  {refining && (
                    <motion.div
                      className="refine-box"
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                    >
                      <span className="refine-hint">Refining: <em>{intentSummary()}</em></span>
                      <div className="refine-row">
                        <input
                          ref={refineRef}
                          type="text"
                          className="input-field"
                          placeholder='e.g. "14 nights instead" or "depart from SYD"'
                          value={refineInput}
                          onChange={e => setRefineInput(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleRefine();
                            if (e.key === 'Escape') setRefining(false);
                          }}
                          disabled={loading}
                        />
                        <button className="btn btn-primary btn-sm" onClick={handleRefine} disabled={loading || !refineInput.trim()}>
                          {loading ? <RefreshCcw className="animate-spin" size={14} /> : 'Update'}
                        </button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setRefining(false)}>Cancel</button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="intent-actions-v2">
                  <button className="btn btn-primary" onClick={handleScout}>
                    <Search size={16} /> Scout Now
                  </button>
                  {!refining && (
                    <button className="btn btn-light" onClick={() => setRefining(true)}>
                      <Pencil size={14} /> Refine
                    </button>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default Planner;
