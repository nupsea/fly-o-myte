/**
 * Shared UI components used across multiple views.
 */
import React, { useState, useEffect, useRef } from 'react'
import {
  Plane,
  Clock,
  ArrowRight,
  X,
} from 'lucide-react'
import { motion } from 'framer-motion'

// ── Utility ──

export const cronToHuman = (cron: string) => {
  if (!cron) return 'Manual';
  if (cron === '0 7 * * *') return 'Daily at 7am';
  if (cron === '0 20 * * *') return 'Daily at 8pm';
  if (cron === '0 0 * * *') return 'Daily at Midnight';
  if (cron === '0 */4 * * *') return 'Every 4 hours';
  if (cron === '0 */12 * * *') return 'Every 12 hours';

  const parts = cron.split(' ');
  if (parts.length === 5) {
    const [m, h, dom, mon, dow] = parts;
    if (dom === '*' && mon === '*' && dow === '*') {
      const hh = h.padStart(2, '0');
      const mm = m.padStart(2, '0');
      return `Daily at ${hh}:${mm}`;
    }
  }
  return 'Custom Schedule';
};

// ── Modal ──

export const Modal = ({ title, children, onClose, wide }: { title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) => (
  <div className="modal-overlay" onClick={onClose}>
    <motion.div 
      className={`modal-content glass ${wide ? 'modal-wide' : ''}`} 
      onClick={e => e.stopPropagation()}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
    >
      <div className="modal-header">
        <h2>{title}</h2>
        <button className="close-btn" onClick={onClose}><X size={20} /></button>
      </div>
      <div className="modal-body">
        {children}
      </div>
    </motion.div>
  </div>
);

// ── JourneyDetails ──

export const JourneyDetails = ({ snapshot, returnDate }: { snapshot: any; returnDate?: string }) => {
  if (!snapshot) return null;
  
  let legs = snapshot.fly_o_myte_legs;
  if (!legs && snapshot.offer_raw) {
    try {
      const raw = typeof snapshot.offer_raw === 'string' ? JSON.parse(snapshot.offer_raw) : snapshot.offer_raw;
      legs = raw.fly_o_myte_legs;
    } catch { /* ignore */ }
  }

  if (!legs) return null;

  const renderLegs = (title: string, journeyLegs: any[]) => {
    if (!journeyLegs || journeyLegs.length === 0) {
      if (title === "Return Journey" && returnDate) {
        return (
          <div className="journey-block">
            <h4 className="journey-title">{title}</h4>
            <div className="legs-list">
              <div className="leg-card glass" style={{alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', textAlign: 'center', padding: '32px 16px', fontStyle: 'italic', fontSize: '0.85rem'}}>
                <Plane size={24} style={{opacity: 0.3, marginBottom: '8px'}} />
                <div>Return legs finalized at booking</div>
                <div style={{fontSize: '0.75rem', marginTop: '4px'}}>Scheduled for {new Date(returnDate).toLocaleDateString([], {month: 'short', day: 'numeric'})}</div>
              </div>
            </div>
          </div>
        );
      }
      return null;
    }
    return (
      <div className="journey-block">
        <h4 className="journey-title">{title}</h4>
        <div className="legs-list">
          {journeyLegs.map((leg, idx) => {
            let layoverMinutes = 0;
            if (idx < journeyLegs.length - 1) {
               const currentArrival = new Date(leg.arrival_time);
               const nextDeparture = new Date(journeyLegs[idx + 1].departure_time);
               if (!isNaN(currentArrival.getTime()) && !isNaN(nextDeparture.getTime())) {
                 layoverMinutes = Math.max(0, Math.floor((nextDeparture.getTime() - currentArrival.getTime()) / 60000));
               }
            }
            const depDate = leg.departure_time ? new Date(leg.departure_time) : null;
            const arrDate = leg.arrival_time ? new Date(leg.arrival_time) : null;
            return (
              <React.Fragment key={idx}>
                <div className="leg-card glass">
                   <div className="leg-airline">
                     <Plane size={14} className="leg-icon"/>
                     <span className="bold">{leg.airline_code}</span> {leg.flight_number}
                   </div>
                   <div className="leg-times">
                     <div className="time-col">
                       <span className="time-val">{depDate && !isNaN(depDate.getTime()) ? depDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '--:--'}</span>
                       <span className="time-port">{leg.departure_airport}</span>
                       {depDate && !isNaN(depDate.getTime()) && <span className="time-date">{depDate.toLocaleDateString([], {month: 'short', day: 'numeric'})}</span>}
                     </div>
                     <div className="leg-arrow"><ArrowRight size={14}/></div>
                     <div className="time-col">
                       <span className="time-val">{arrDate && !isNaN(arrDate.getTime()) ? arrDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '--:--'}</span>
                       <span className="time-port">{leg.arrival_airport}</span>
                       {arrDate && !isNaN(arrDate.getTime()) && <span className="time-date">{arrDate.toLocaleDateString([], {month: 'short', day: 'numeric'})}</span>}
                     </div>
                     <div className="leg-duration">
                       <Clock size={12}/> {Math.floor((leg.duration_minutes || 0) / 60)}h {(leg.duration_minutes || 0) % 60}m
                     </div>
                   </div>
                </div>
                {layoverMinutes > 0 && (
                  <div className="layover-divider">
                    <div className="layover-line"></div>
                    <span className="layover-text">Layover: {Math.floor(layoverMinutes / 60)}h {layoverMinutes % 60}m</span>
                    <div className="layover-line"></div>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="journey-details">
      {renderLegs("Onward Journey", legs.onward)}
      {renderLegs("Return Journey", legs.return)}
    </div>
  );
};

// ── AirportInput ──

export const AirportInput = ({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (val: string) => void; placeholder?: string }) => {
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [show, setShow] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (value.length > 1) {
      fetch(`/api/airports/search?q=${value}`)
        .then(res => res.json())
        .then(data => setSuggestions(data));
    } else {
      setSuggestions([]);
    }
  }, [value]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShow(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="input-group airport-group" ref={containerRef}>
      <label>{label}</label>
      <input 
        type="text" 
        value={value} 
        onChange={e => { onChange(e.target.value); setShow(true); }}
        onFocus={() => setShow(true)}
        placeholder={placeholder}
        className="input-field"
      />
      {show && suggestions.length > 0 && (
        <div className="suggestions-dropdown glass">
          {suggestions.map(s => (
            <div 
              key={s.value} 
              className="suggestion-item" 
              onClick={() => { onChange(s.value); setShow(false); }}
            >
              <span className="s-code">{s.value}</span>
              <span className="s-label">{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
