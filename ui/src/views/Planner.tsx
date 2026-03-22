/**
 * AI Planner view — natural language journey modeling.
 */
import { useState } from 'react'
import {
  Sparkles,
  Plane,
  RefreshCcw,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

const Planner = () => {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [intent, setIntent] = useState<any>(null);

  const handlePlan = async () => {
    if (!input) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/planner?intent_text=${encodeURIComponent(input)}`, { method: 'POST' });
      const data = await res.json();
      setIntent(data);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  return (
    <div className="view planner-view">
      <header className="view-header">
        <h1>AI Planner</h1>
        <p className="subtitle">Natural language journey modeling</p>
      </header>

      <div className="planner-container glass">
        <div className="omnibox">
          <Sparkles className="sparkle-icon" size={24} />
          <input 
            type="text" 
            placeholder="Where to? e.g. 'Bangalore in December to Jan for 25 days'" 
            className="planner-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePlan()}
          />
          <button className="btn btn-primary" onClick={handlePlan} disabled={loading}>
            {loading ? <RefreshCcw className="animate-spin" /> : <span>Plan Journey</span>}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {intent && (
          <motion.div className="intent-result glass" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="intent-header">
              <div className="destination-badge">
                <Plane size={20} />
                <span>{intent.destination_display}</span>
              </div>
              <div className="intent-meta">
                <span>{intent.month}/{intent.year}</span>
                <span className="dot" />
                <span>{intent.nights} nights</span>
              </div>
            </div>
            <div className="intent-actions">
              <button className="btn btn-primary">Start Scouting {intent.destination_iata}</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Planner;
