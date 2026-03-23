/**
 * Smart Scout view — exploration engine for family flight windows.
 */
import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Search,
  Plane,
  Clock,
  RefreshCcw,
  AlertCircle,
  CalendarX,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { AirportInput, JourneyDetails } from '../components/shared'

const Scout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [origin, setOrigin] = useState('BNE');
  const [dest, setDest] = useState('');
  const [mode, setMode] = useState<'flexible' | 'exact'>('flexible');

  const availableMonths = Array.from({ length: 12 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() + i);
    const m = d.toLocaleString('en-US', { month: 'short' }).toLowerCase();
    return `${m}-${d.getFullYear()}`;
  });

  const [months, setMonths] = useState<string[]>([availableMonths[0]]);
  const [tripLen, setTripLen] = useState(14);
  const [departDate, setDepartDate] = useState('');
  const [returnDate, setReturnDate] = useState('');
  const [scoutFlexDays, setScoutFlexDays] = useState(3);
  const [scouting, setScouting] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [searched, setSearched] = useState(false);  // true after first scout attempt
  const [error, setError] = useState<string | null>(null);
  const [plannerHint, setPlannerHint] = useState<string | null>(null);

  const calculateMaxDays = (selectedMonths: string[]) => {
    if (selectedMonths.length === 0) return 0;
    const parsed = selectedMonths.map(m => {
      const [mon, year] = m.split('-');
      const monthIdx = new Date(Date.parse(mon + " 1, 2012")).getMonth();
      return { month: monthIdx, year: parseInt(year) };
    }).sort((a, b) => (a.year * 12 + a.month) - (b.year * 12 + b.month));
    let totalDays = 0;
    parsed.forEach(p => {
      totalDays += new Date(p.year, p.month + 1, 0).getDate();
    });
    return totalDays;
  };

  const toggleMonth = (m: string) => {
    setError(null);
    const mIdx = availableMonths.indexOf(m);
    
    setMonths(prev => {
      if (prev.includes(m)) return prev.filter(x => x !== m);
      if (prev.length === 0) return [m];
      if (prev.length === 1) {
        const currentIdx = availableMonths.indexOf(prev[0]);
        if (Math.abs(mIdx - currentIdx) > 3) return [m];
      }
      const allSelectedIndices = [...prev.map(p => availableMonths.indexOf(p)), mIdx].sort((a, b) => a - b);
      const span = allSelectedIndices[allSelectedIndices.length - 1] - allSelectedIndices[0];
      if (allSelectedIndices.length > 4) {
        setError("Maximum 4 months can be scouted at once.");
        return prev;
      }
      if (span > 3) {
        setError("Selected months must be within a 3-month range.");
        return prev;
      }
      return [...prev, m].sort((a, b) => availableMonths.indexOf(a) - availableMonths.indexOf(b));
    });
  };

  const maxPossibleDays = calculateMaxDays(months);
  
  useEffect(() => {
    if (mode === 'flexible' && tripLen > maxPossibleDays) {
      setTripLen(Math.max(1, Math.min(14, maxPossibleDays)));
    }
  }, [months, mode]);

  // Pre-fill from AI Planner navigation state (no auto-trigger — user reviews and clicks Scout)
  useEffect(() => {
    const sp = location.state?.scoutParams;
    const hint = location.state?.plannerHint;
    if (!sp) return;

    setOrigin(sp.origin || 'BNE');
    setDest(sp.destination || '');
    if (hint) setPlannerHint(hint);

    if (sp.months) {
      setMode('flexible');
      setMonths(sp.months);
      if (sp.trip_length) setTripLen(sp.trip_length);
    } else if (sp.depart_date && sp.return_date) {
      setMode('exact');
      setDepartDate(sp.depart_date);
      setReturnDate(sp.return_date);
      if (sp.flex_days != null) setScoutFlexDays(sp.flex_days);
    }

    // Clear router state so back-navigation doesn't re-trigger
    window.history.replaceState({}, '');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleScout = () => {
    setScouting(true);
    setError(null);

    const body: any = { origin, destination: dest, flex_days: scoutFlexDays };
    if (mode === 'flexible') {
      body.months = months;
      body.trip_length = tripLen;
    } else {
      if (!departDate || !returnDate) {
        setError("Please select both departure and return dates.");
        setScouting(false);
        return;
      }
      body.depart_date = departDate;
      body.return_date = returnDate;
    }

    fetch('/api/scout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Scouting failed");
        return data;
      })
      .then(data => { setResults(data); setScouting(false); setSearched(true); })
      .catch(err => {
        setError(err.message);
        setScouting(false);
        setSearched(true);
      });
  };

  return (
    <div className="view scout-view">
      <header className="view-header">
        <h1>Smart Scout</h1>
        <p className="subtitle">Exploration engine for family flight windows</p>
      </header>

      {plannerHint && (
        <div className="planner-origin-banner">
          <span className="planner-origin-label">From AI Planner</span>
          <span>{plannerHint}</span>
          <button className="btn-icon" style={{ padding: '2px 6px', fontSize: '0.75rem' }} onClick={() => setPlannerHint(null)}>×</button>
        </div>
      )}

      {error && (
        <motion.div className="error-banner glass" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </motion.div>
      )}

      <div className="scout-controls glass" style={{ position: 'relative' }}>
        <div className="scout-mode-tabs">
          <button className={`mode-tab ${mode === 'flexible' ? 'active' : ''}`} onClick={() => setMode('flexible')}>Flexible Months</button>
          <button className={`mode-tab ${mode === 'exact' ? 'active' : ''}`} onClick={() => setMode('exact')}>Exact Dates</button>
        </div>

        <AnimatePresence>
          {scouting && (
            <motion.div
              className="scout-loading-overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                style={{ display: 'flex' }}
              >
                <RefreshCcw size={36} style={{ color: 'var(--primary)' }} />
              </motion.div>
              <p style={{ margin: 0, fontWeight: 700, fontSize: '1rem', color: 'var(--text-main)' }}>
                {mode === 'flexible' ? `Scouting ${months.length} month${months.length !== 1 ? 's' : ''}...` : 'Scouting exact dates...'}
              </p>
              <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                Checking fares across airlines. This may take a moment.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="search-grid">
          <AirportInput label="From (Origin)" value={origin} onChange={setOrigin} />
          <AirportInput label="To (Destination)" value={dest} onChange={setDest} placeholder="e.g. London, Bali, SYD" />
          
          {mode === 'flexible' ? (
            <>
              <div className="input-group" style={{ gridColumn: 'span 2' }}>
                <label>Select Months (Max 3-month span)</label>
                <div className="month-picker">
                  {availableMonths.map(m => (
                    <button 
                      key={m} 
                      className={`month-btn ${months.includes(m) ? 'active' : ''}`}
                      onClick={() => toggleMonth(m)}
                    >
                      {m.replace('-', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              <div className="input-group">
                <label>Trip Length (Nights)</label>
                <select
                  value={tripLen}
                  onChange={e => setTripLen(parseInt(e.target.value))}
                  className="select-field"
                >
                  {[...Array(Math.min(90, maxPossibleDays))].map((_, i) => (
                    <option key={i+1} value={i+1}>{i+1} {i+1 === 1 ? 'night' : 'nights'}</option>
                  ))}
                </select>
              </div>
            </>
          ) : (
            <>
              <div className="input-group">
                <label>Departure Date</label>
                <input type="date" value={departDate} onChange={e => setDepartDate(e.target.value)} className="input-field" min={new Date().toISOString().split('T')[0]} />
              </div>
              <div className="input-group">
                <label>Return Date</label>
                <input type="date" value={returnDate} onChange={e => setReturnDate(e.target.value)} className="input-field" min={departDate || new Date().toISOString().split('T')[0]} />
              </div>
            </>
          )}

          <div className="input-group">
            <label>Date Flex (±days)</label>
            <input
              type="number"
              min={0}
              max={14}
              value={scoutFlexDays}
              onChange={e => setScoutFlexDays(Math.max(0, Math.min(14, parseInt(e.target.value) || 0)))}
              className="input-field"
              placeholder="3"
            />
          </div>
        </div>
        <button className="btn btn-primary btn-lg" onClick={handleScout} disabled={scouting || !origin || !dest || (mode === 'flexible' && months.length === 0) || (mode === 'exact' && (!departDate || !returnDate))}>
          {scouting ? <RefreshCcw className="animate-spin" /> : <Search />}
          <span>{mode === 'flexible' ? 'Explore Selected Months' : 'Search Exact Dates'}</span>
        </button>
      </div>

      {searched && !scouting && results.length === 0 && !error && (
        <motion.div className="scout-empty glass" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <CalendarX size={32} style={{ color: 'var(--text-muted)' }} />
          <p style={{ fontWeight: 700, margin: '8px 0 4px' }}>No flights found</p>
          {mode === 'exact' ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: 0 }}>
              Flight data for these exact dates may not be available yet — typically bookings open 3–6 months out.
              Try switching to <strong>Flexible Months</strong> mode to explore the broader period.
            </p>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', margin: 0 }}>
              No results for the selected months and trip length. Try different months or a shorter trip.
            </p>
          )}
          {mode === 'exact' && (
            <button className="btn btn-light" style={{ marginTop: 12 }} onClick={() => {
              setMode('flexible');
              // Convert exact dates to approximate month string
              if (departDate) {
                const d = new Date(departDate);
                const m = d.toLocaleString('en-US', { month: 'short' }).toLowerCase();
                const approxMonth = `${m}-${d.getFullYear()}`;
                if (availableMonths.includes(approxMonth)) setMonths([approxMonth]);
              }
              setResults([]);
              setSearched(false);
            }}>
              Switch to Flexible Months
            </button>
          )}
        </motion.div>
      )}

      <div className="scout-results-grid">
        {results.map((r, i) => {
          const dDate = new Date(r.depart_date);
          const rDate = new Date(r.return_date);
          const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
          const rawBd = r.breakdown || {};
          const bd = {
            base_adults: rawBd.base_fare_adults ?? rawBd.base_adults ?? 0,
            base_children: rawBd.base_fare_children ?? rawBd.base_children ?? 0,
            bags: rawBd.bag_fees ?? rawBd.bags ?? 0,
            seats: rawBd.seat_fees ?? rawBd.seats ?? 0,
            infant: rawBd.infant_fees ?? rawBd.infant ?? 0,
          };
          
          return (
            <div key={i} className="scout-result-card glass">
              <div className="r-top">
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', paddingTop: '3px', minWidth: '20px' }}>#{i + 1}</span>
                  <div className="r-date-info">
                    <div className="r-dates">
                      {days[dDate.getDay()]}, {dDate.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })} — {days[rDate.getDay()]}, {rDate.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}
                    </div>
                    <div className="dim-text" style={{ fontSize: '0.75rem' }}>{r.trip_length_days} nights total</div>
                  </div>
                </div>
                {r.school_holiday && <span className="r-holiday-badge">{r.school_holiday.label}</span>}
              </div>
              
              <div className="r-body" style={{flexDirection: 'column', alignItems: 'stretch', gap: '16px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end'}}>
                  <div className="r-flight-details">
                    <div className="r-airline">
                      <span className="a-code">{r.airline_code} {r.flight_number || ''}</span>
                      <span className="a-stops">{r.stops === 0 ? 'Non-stop' : `${r.stops} stops`}</span>
                    </div>
                    <div className="r-times">
                      <div className="r-time-row"><Plane size={10} style={{ transform: 'rotate(90deg)' }} /> {r.departure_time} — {r.arrival_time}</div>
                      {r.return_departure_time && (
                        <div className="r-time-row"><Plane size={10} style={{ transform: 'rotate(270deg)' }} /> {r.return_departure_time} — {r.return_arrival_time}</div>
                      )}
                      <div className="r-duration"><Clock size={10} /> {Math.floor(r.duration_minutes / 60)}h {r.duration_minutes % 60}m</div>
                    </div>
                  </div>
                  
                  <div className="r-price-section">
                    <div className="r-price">${r.true_family_cost.toLocaleString()}</div>
                    <div className="r-breakdown-mini">
                      <span>Base: ${(bd.base_adults || 0) + (bd.base_children || 0)}</span>
                      <span>Fees: ${(bd.bags || 0) + (bd.seats || 0) + (bd.infant || 0)}</span>
                    </div>
                  </div>
                </div>
                <JourneyDetails snapshot={r} returnDate={r.return_date} />
              </div>
              
              <button className="btn btn-light btn-full" onClick={() => {
                fetch('/api/trips', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    origin,
                    destination: dest,
                    depart_date: r.depart_date,
                    return_date: r.return_date,
                    label: `${origin}-${dest} (${days[dDate.getDay()]} ${dDate.getDate()} ${dDate.toLocaleString('default', { month: 'short' })})`,
                    offer_seed: {
                      base_fare_per_adult: r.base_fare_per_adult,
                      true_family_cost: r.true_family_cost,
                      true_cost_breakdown: r.breakdown ? {
                        base_adults: r.breakdown.base_fare_adults ?? r.breakdown.base_adults ?? 0,
                        base_children: r.breakdown.base_fare_children ?? r.breakdown.base_children ?? 0,
                        bags: r.breakdown.bag_fees ?? r.breakdown.bags ?? 0,
                        seats: r.breakdown.seat_fees ?? r.breakdown.seats ?? 0,
                        infant: r.breakdown.infant_fees ?? r.breakdown.infant ?? 0,
                        total: r.breakdown.total ?? r.true_family_cost,
                      } : { total: r.true_family_cost },
                      airline_code: r.airline_code,
                      stops: r.stops,
                      departure_time: r.departure_time,
                      return_departure_time: r.return_departure_time,
                      return_arrival_time: r.return_arrival_time,
                      duration_minutes: r.duration_minutes,
                      offer_raw: r.offer_raw || null,
                    }
                  })
                }).then(() => navigate('/'));
              }}>Watch This Window</button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Scout;
