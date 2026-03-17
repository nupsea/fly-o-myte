import React, { useState, useEffect, useRef } from 'react'
import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Search, 
  Sparkles, 
  Activity, 
  Users, 
  Plane,
  ChevronRight,
  TrendingDown,
  Clock,
  RefreshCcw,
  CalendarDays,
  X,
  Settings,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Trash2,
  Save,
  Plus
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import './App.css'

// ── Shared UI Components ──

const Modal = ({ title, children, onClose, wide }: { title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) => (
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

const cronToHuman = (cron: string) => {
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

const JourneyDetails = ({ snapshot, returnDate }: { snapshot: any; returnDate?: string }) => {
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

const AirportInput = ({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (val: string) => void; placeholder?: string }) => {
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

// ── Main Views ──

const Sidebar = () => {
  const navItems = [
    { to: "/", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/scout", icon: Search, label: "Smart Scout" },
    { to: "/planner", icon: Sparkles, label: "AI Planner" },
    { to: "/monitoring", icon: Activity, label: "Monitoring" },
    { to: "/profile", icon: Users, label: "Family Profile" },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-container">
          <Plane className="logo-icon" />
          <span className="logo-text">Fly-O-Myte</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <item.icon className="nav-icon" size={20} />
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="profile-mini">
          <div className="avatar">B</div>
          <div className="profile-info">
            <span className="profile-name">Brisbane Family</span>
            <span className="profile-status">Premium</span>
          </div>
        </div>
      </div>
    </aside>
  );
};

const TripSettingsModal = ({ trip, profile, onClose, onSave, onDelete }: { trip: any, profile: any, onClose: () => void, onSave: (id: number, data: any) => void, onDelete: (id: number) => void }) => {
  const [formData, setFormData] = useState({
    label: trip.label,
    adults: trip.adults,
    children: (trip.children && trip.children.length > 0) ? trip.children : (profile?.children || []),
    bags_per_person: trip.bags_per_person,
    max_stops: trip.max_stops,
    alert_email: trip.alert_email,
    alert_threshold_aud: trip.alert_threshold_aud,
    group_tag: trip.group_tag,
    cron_schedule: trip.cron_schedule
  });

  return (
    <Modal title={`Trip Settings: ${trip.label}`} onClose={onClose}>
      <div className="settings-form">
        <div className="input-group">
          <label>Label</label>
          <input type="text" value={formData.label} onChange={e => setFormData({...formData, label: e.target.value})} className="input-field" />
        </div>
        <div className="row">
          <div className="input-group">
            <label>Adults</label>
            <input type="number" value={formData.adults} onChange={e => setFormData({...formData, adults: parseInt(e.target.value)})} className="input-field" />
          </div>
          <div className="input-group">
            <label>Bags</label>
            <input type="number" value={formData.bags_per_person} onChange={e => setFormData({...formData, bags_per_person: parseInt(e.target.value)})} className="input-field" />
          </div>
        </div>

        <div className="children-list" style={{ marginBottom: '20px' }}>
          <label>Children</label>
          {formData.children.map((c: any, i: number) => (
            <div key={i} className="child-row" style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
              <input type="text" value={c.name} onChange={e => {
                const newChildren = [...formData.children];
                newChildren[i].name = e.target.value;
                setFormData({...formData, children: newChildren});
              }} className="input-field" placeholder="Name" />
              <input type="date" value={c.dob} onChange={e => {
                const newChildren = [...formData.children];
                newChildren[i].dob = e.target.value;
                setFormData({...formData, children: newChildren});
              }} className="input-field" />
              <button type="button" className="btn-icon" onClick={() => {
                setFormData({...formData, children: formData.children.filter((_: any, idx: number) => idx !== i)});
              }}><Trash2 size={16} /></button>
            </div>
          ))}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
            setFormData({...formData, children: [...formData.children, {name: '', dob: ''}]})
          }}><Plus size={14} /> Add Child</button>
        </div>

        <div className="input-group">
          <label>Max Stops</label>
          <select value={formData.max_stops} onChange={e => setFormData({...formData, max_stops: parseInt(e.target.value)})} className="select-field">
            <option value="0">Non-stop</option>
            <option value="1">Up to 1 stop</option>
            <option value="2">Up to 2 stops</option>
          </select>
        </div>
        <div className="row">
          <div className="input-group">
            <label>Alert Email</label>
            <input 
              type="email" 
              value={formData.alert_email || ''} 
              onChange={e => setFormData({...formData, alert_email: e.target.value || null})} 
              className="input-field" 
              placeholder={`Default: ${profile?.alert_email || 'Not set'}`} 
            />
          </div>
          <div className="input-group">
            <label>Budget Threshold (AUD)</label>
            <input 
              type="number" 
              value={formData.alert_threshold_aud || ''} 
              onChange={e => setFormData({...formData, alert_threshold_aud: e.target.value ? parseFloat(e.target.value) : null})} 
              className="input-field" 
              placeholder="No limit" 
            />
          </div>
        </div>
        <div className="input-group">
          <label>Group Tag (for multi-option sets)</label>
          <input type="text" value={formData.group_tag || ''} onChange={e => setFormData({...formData, group_tag: e.target.value || null})} className="input-field" placeholder="e.g. Europe-Summer-26" />
        </div>
        <div className="input-group">
          <label>Polling Schedule</label>
          <select value={formData.cron_schedule} onChange={e => setFormData({...formData, cron_schedule: e.target.value})} className="select-field">
            <option value="0 7 * * *">Daily at 7am</option>
            <option value="0 20 * * *">Daily at 8pm</option>
            <option value="0 0 * * *">Daily at Midnight</option>
            <option value="0 */4 * * *">Every 4 hours</option>
            <option value="0 */12 * * *">Every 12 hours</option>
          </select>
        </div>
        <div className="modal-actions">
          <button className="btn btn-danger" onClick={() => onDelete(trip.id)}>Delete Trip</button>
          <button className="btn btn-primary" onClick={() => onSave(trip.id, formData)}>Save Changes</button>
        </div>
      </div>
    </Modal>
  );
};

const Dashboard = () => {
  const [trips, setTrips] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrip, setSelectedTrip] = useState<any>(null); // For Settings
  const [detailsTrip, setDetailsTrip] = useState<any>(null); // For Details/History
  const [tripHistory, setTripHistory] = useState<any[]>([]);
  const [flexTrip, setFlexTrip] = useState<any>(null);
  const [flexResults, setFlexResults] = useState<any[]>([]);
  const [flexLoading, setFlexLoading] = useState(false);
  const [flexError, setFlexError] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);

  const fetchTrips = () => {
    setLoading(true);
    fetch('/api/trips')
      .then(res => res.json())
      .then(data => {
        setTrips(data);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchTrips();
    fetch('/api/profile').then(res => res.json()).then(setProfile);
    const handler = () => fetchTrips();
    window.addEventListener('fom:recomputed', handler);
    return () => window.removeEventListener('fom:recomputed', handler);
  }, []);

  const [flexDays, setFlexDays] = useState(3);

  const openFlex = (trip: any) => {
    setFlexTrip(trip);
    setFlexLoading(true);
    setFlexError(null);
    setFlexResults([]);
    fetch(`/api/trips/${trip.id}/flex?flex_days=${flexDays}`)
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
        return data;
      })
      .then(data => {
        setFlexResults(data);
        setFlexLoading(false);
      })
      .catch(err => {
        setFlexError(err.message);
        setFlexLoading(false);
      });
  };

  const openDetails = (trip: any) => {
    setDetailsTrip(trip);
    fetch(`/api/trips/${trip.id}/history`)
      .then(res => res.json())
      .then(data => {
        setTripHistory(data);
      });
  };

  const handleRefresh = (tid: number) => {
    fetch(`/api/trips/${tid}/refresh`, { method: 'POST' }).then(() => fetchTrips());
  };

  const handleDelete = (tid: number) => {
    if (confirm("Delete this trip?")) {
      fetch(`/api/trips/${tid}`, { method: 'DELETE' }).then(() => fetchTrips());
    }
  };

  const updateTrip = (tid: number, data: any) => {
    fetch(`/api/trips/${tid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(() => { fetchTrips(); setSelectedTrip(null); });
  };

  return (
    <div className="view dashboard-view">
      <header className="view-header">
        <div className="header-content">
          <h1>Command Center</h1>
          <p className="subtitle">Real-time tracking of {trips.length} journeys</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-primary" onClick={() => fetch('/api/poll', {method: 'POST'}).then(() => fetchTrips())}>
            <RefreshCcw size={16} />
            <span>Poll All</span>
          </button>
        </div>
      </header>

      <div className="trip-grid">
        {trips.map((trip) => (
          <motion.div key={trip.id} className="trip-card glass" layoutId={`card-${trip.id}`}>
            <div className="card-top">
              <div className="route">
                <span className="iata">{trip.origin}</span>
                <ChevronRight size={14} />
                <span className="iata">{trip.destination}</span>
              </div>
              <div className="actions-top">
                 <button className="btn-icon" onClick={() => setSelectedTrip(trip)} title="Settings"><Settings size={16} /></button>
                 <div className={`status-badge status-${trip.recommendation?.decision || 'monitor'}`}>
                   {trip.recommendation?.decision?.replace('_', ' ') || 'monitoring'}
                 </div>
              </div>
            </div>

            <div className="card-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div className="trip-dates">
                  <CalendarDays size={14} />
                  <span>{trip.depart_date}</span>
                  {trip.return_date && <span> — {trip.return_date}</span>}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={12} /> {cronToHuman(trip.cron_schedule)}
                </div>
              </div>

              {trip.depart_date && trip.return_date && (
                <div style={{ marginBottom: '8px' }}>
                  <span className="trip-days-badge">
                    {Math.round((new Date(trip.return_date).getTime() - new Date(trip.depart_date).getTime()) / 86400000)} days
                  </span>
                </div>
              )}
              
              {trip.latest_snapshot && (
                <div className="flight-info-summary" style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                  <strong>{trip.latest_snapshot.airline_code}</strong> &middot; {trip.latest_snapshot.stops} stop{trip.latest_snapshot.stops !== 1 ? 's' : ''} &middot; departs {trip.latest_snapshot.departure_time}
                </div>
              )}

              <div className="price-display">
                <span className="price">${trip.latest_snapshot?.true_family_cost?.toLocaleString() || '---'}</span>
                <span className="currency">AUD</span>
              </div>
              {trip.recommendation && (
                <div className="savings-meter">
                  <div className="meter-label">
                    <span>{trip.recommendation.price_level_signal} Price Level</span>
                    <span className="savings-value">
                      {trip.recommendation.trend_slope < 0 ? <TrendingDown size={12} /> : null}
                      {Math.abs(trip.recommendation.trend_slope).toFixed(0)} AUD/day
                    </span>
                  </div>
                  <div className="meter-track">
                    <div className="meter-fill" style={{ width: `${Math.min(100, (trip.recommendation.confidence * 100))}%` }} />
                  </div>
                </div>
              )}
            </div>

            <div className="card-footer">
              <button className="btn btn-ghost btn-sm" onClick={() => openDetails(trip)}>Details & History</button>
              <button className="btn btn-light btn-sm" onClick={() => openFlex(trip)}>Find Better Dates</button>
              <button className="btn btn-icon btn-sm" onClick={() => handleRefresh(trip.id)} title="Manual Refresh"><RefreshCcw size={14} /></button>
            </div>
          </motion.div>
        ))}
      </div>

      <AnimatePresence>
        {detailsTrip && (
          <Modal wide title={`Details: ${detailsTrip.label}`} onClose={() => setDetailsTrip(null)}>
            <div className="details-content">
              <div className="details-header">
                <div className="dh-left">
                  <h3>True Family Cost Breakdown</h3>
                  <p className="dim-text">
                    Based on your family profile.
                    {detailsTrip.depart_date && detailsTrip.return_date && (
                      <span style={{ marginLeft: '8px', fontWeight: 600, color: 'var(--text-main)' }}>
                        {Math.round((new Date(detailsTrip.return_date).getTime() - new Date(detailsTrip.depart_date).getTime()) / 86400000)} days total.
                      </span>
                    )}
                  </p>
                  {detailsTrip.latest_snapshot && (
                    <div style={{ marginTop: '8px', fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-main)' }}>
                      Flight: {detailsTrip.latest_snapshot.airline_code} &middot; {detailsTrip.latest_snapshot.stops} stops &middot; Departs: {detailsTrip.latest_snapshot.departure_time}
                    </div>
                  )}
                </div>
                <div className="dh-right">
                  <span className="dh-price">${detailsTrip.latest_snapshot?.true_family_cost?.toLocaleString()}</span>
                </div>
              </div>
              
              <div className="price-breakdown">
                 {(() => {
                   try {
                     const bd = JSON.parse(detailsTrip.latest_snapshot?.true_cost_breakdown || '{}');
                     return (
                       <ul className="bd-list">
                         <li><span>Base Fares:</span> <span>${(bd.base_adults || 0) + (bd.base_children || 0)}</span></li>
                         <li><span>Bags ({detailsTrip.bags_per_person} per pax):</span> <span>${bd.bags || 0}</span></li>
                         <li><span>Seat Selection:</span> <span>${bd.seats || 0}</span></li>
                         <li><span>Infant Fees:</span> <span>${bd.infant || 0}</span></li>
                       </ul>
                     );
                   } catch { return <p>No breakdown available.</p>; }
                 })()}
              </div>

              <JourneyDetails snapshot={detailsTrip.latest_snapshot} returnDate={detailsTrip.return_date} />

              <div className="history-section">
                 <h3>Price History & Alternatives</h3>
                 {tripHistory.length === 0 ? <p className="dim-text">Loading history...</p> : (
                   <div className="history-list">
                     {Object.entries(
                       tripHistory.reduce((acc: any, snap: any) => {
                         // Group by exactly matching timestamp to ensure options from the same poll are grouped
                         const timeKey = new Date(snap.fetched_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
                         if (!acc[timeKey]) acc[timeKey] = [];
                         acc[timeKey].push(snap);
                         return acc;
                       }, {})
                     ).map(([timeStr, snaps]: [string, any], groupIdx) => (
                       <div key={groupIdx} className="history-group">
                         <div className="history-group-header">
                           <Clock size={14} className="hg-icon" />
                           <span>{timeStr}</span>
                         </div>
                         <div className="history-group-items">
                           {snaps
                             // Sort ascending by price (cheapest first, rank 1 at top)
                             .sort((a: any, b: any) => a.true_family_cost - b.true_family_cost)
                             .map((snap: any, i: number) => {
                             const isRank1 = snap.rank === 1;
                             return (
                               <div key={i} className={`history-row ${isRank1 ? 'rank-1' : 'rank-alt'}`}>
                                 <div className="h-left">
                                   <div className="h-flight-info">
                                     <span className={`r-badge ${isRank1 ? 'primary' : 'muted'}`}>Rank {snap.rank || 1}</span>
                                     <span className="h-airline">{snap.airline_code}</span>
                                     <span className="h-stops">{snap.stops} stop{snap.stops !== 1 ? 's' : ''}</span>
                                     <span className="h-time">dep {snap.departure_time}</span>
                                   </div>
                                 </div>
                                 <span className="h-price">${snap.true_family_cost}</span>
                               </div>
                             );
                           })}
                         </div>
                       </div>
                     ))}
                   </div>
                 )}
              </div>
            </div>
          </Modal>
        )}

        {selectedTrip && (
          <TripSettingsModal 
            trip={selectedTrip} 
            profile={profile}
            onClose={() => setSelectedTrip(null)} 
            onSave={updateTrip}
            onDelete={handleDelete}
          />
        )}

        {flexTrip && (
          <Modal wide title={`Date Optimizer: ${flexTrip.origin} → ${flexTrip.destination}`} onClose={() => { setFlexTrip(null); setFlexResults([]); setFlexLoading(false); setFlexError(null); }}>
            {flexLoading ? (
              <div className="flex-loading-state">
                <p className="dim-text" style={{ textAlign: 'center', marginBottom: '16px' }}>Scouting nearby dates across multiple airlines. This may take a moment...</p>
                <div className="progress-bar-container">
                  <motion.div
                    className="progress-bar-fill"
                    initial={{ width: "0%" }}
                    animate={{ width: "100%" }}
                    transition={{ duration: 5, ease: "easeInOut", repeat: Infinity }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex-results-list">
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
                  <p className="dim-text" style={{ margin: 0 }}>Showing ±{flexDays} day alternatives ranked by true family cost.</p>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: 'auto' }}>
                    <label style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>Flex (days)</label>
                    <input
                      type="number"
                      min={1}
                      max={14}
                      value={flexDays}
                      onChange={e => setFlexDays(Math.max(1, Math.min(14, parseInt(e.target.value) || 3)))}
                      className="input-field"
                      style={{ width: '64px', padding: '4px 8px', fontSize: '0.875rem' }}
                    />
                    <button className="btn btn-ghost btn-sm" onClick={() => openFlex(flexTrip)}>Re-search</button>
                  </div>
                </div>
                {flexError ? (
                  <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)' }}>
                    <AlertCircle size={20} style={{ marginBottom: '8px', opacity: 0.6 }} />
                    <p style={{ margin: 0, fontSize: '0.875rem' }}>Search failed: {flexError}</p>
                  </div>
                ) : flexResults.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)' }}>
                    <Plane size={20} style={{ marginBottom: '8px', opacity: 0.3 }} />
                    <p style={{ margin: 0, fontSize: '0.875rem' }}>No flights found in the ±{flexDays} day window around {flexTrip?.depart_date}.</p>
                    <p style={{ margin: '6px 0 0', fontSize: '0.8rem', opacity: 0.7 }}>Try increasing Flex days, or the price source may not cover this route.</p>
                  </div>
                ) : (
                  flexResults.map((r, i) => {
                    const dD = new Date(r.depart_date);
                    const rD = new Date(r.return_date);
                    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

                    return (
                      <div key={i} className={`flex-row-enhanced ${r.true_family_cost < flexTrip.latest_snapshot?.true_family_cost ? 'better' : ''}`} style={{flexDirection: 'column', alignItems: 'stretch', gap: '16px'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', minWidth: '24px', paddingTop: '4px' }}>#{i + 1}</span>
                          <div className="f-main-info">
                            <div className="f-dates-v2">
                              <div className="f-date-block">
                                <span className="f-day">{days[dD.getDay()]}</span>
                                <span className="f-date">{dD.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}</span>
                              </div>
                              <ArrowRight size={14} className="f-arrow" />
                              <div className="f-date-block">
                                <span className="f-day">{days[rD.getDay()]}</span>
                                <span className="f-date">{rD.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}</span>
                              </div>
                            </div>

                            <div className="f-flight-info">
                              <div className="f-airline-row">
                                <span className="f-carrier">{r.airline_code}</span>
                                <span className="f-stops">{r.stops === 0 ? 'Non-stop' : `${r.stops} stops`}</span>
                              </div>
                              <div className="f-time-details">
                                <div className="f-time-row">
                                  <Plane size={12} style={{ transform: 'rotate(90deg)', opacity: 0.6 }} />
                                  <span>{r.departure_time} — {r.arrival_time}</span>
                                </div>
                                {r.return_departure_time && (
                                  <div className="f-time-row">
                                    <Plane size={12} style={{ transform: 'rotate(270deg)', opacity: 0.6 }} />
                                    <span>{r.return_departure_time} — {r.return_arrival_time}</span>
                                  </div>
                                )}
                                <div className="f-duration-row">
                                  <Clock size={10} />
                                  <span>{Math.floor(r.duration_minutes / 60)}h {r.duration_minutes % 60}m total</span>
                                </div>
                              </div>
                            </div>
                          </div>
                          </div>

                          <div className="f-pricing-actions">
                            <div className="f-price-block">
                              <span className="f-amount">${r.true_family_cost.toLocaleString()}</span>
                              {r.true_family_cost < flexTrip.latest_snapshot?.true_family_cost && (
                                <span className="f-savings">Save ${(flexTrip.latest_snapshot?.true_family_cost - r.true_family_cost).toFixed(0)}</span>
                              )}
                            </div>
                            <button className="btn btn-primary btn-sm" onClick={() => {
                              fetch(`/api/trips/${flexTrip.id}/replace`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ depart_date: r.depart_date, return_date: r.return_date })
                              }).then(() => {
                                fetchTrips();
                                setFlexTrip(null);
                              });
                            }}>Select Window</button>
                          </div>
                        </div>
                        <JourneyDetails snapshot={r} returnDate={r.return_date} />
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </Modal>
        )}      </AnimatePresence>
    </div>
  );
};

const Scout = () => {
  const navigate = useNavigate();
  const [origin, setOrigin] = useState('BNE');
  const [dest, setDest] = useState('');
  const [mode, setMode] = useState<'flexible' | 'exact'>('flexible');
  
  // Generate next 12 months dynamically
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
  const [error, setError] = useState<string | null>(null);

  // Smart Calendar Utility: Calculate total days in selected months
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
      // If already selected, remove it
      if (prev.includes(m)) {
        return prev.filter(x => x !== m);
      }

      // If we have nothing selected, just select it
      if (prev.length === 0) return [m];

      // SMART SWITCH: If only 1 month is selected and the new one is far away,
      // just switch to the new one instead of erroring.
      if (prev.length === 1) {
        const currentIdx = availableMonths.indexOf(prev[0]);
        if (Math.abs(mIdx - currentIdx) > 3) {
          return [m];
        }
      }

      // Check constraints for multi-selection
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
  
  // Adjust trip length if it exceeds new max
  useEffect(() => {
    if (mode === 'flexible' && tripLen > maxPossibleDays) {
      setTripLen(Math.max(1, Math.min(14, maxPossibleDays)));
    }
  }, [months, mode]);

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
      .then(data => { setResults(data); setScouting(false); })
      .catch(err => {
        setError(err.message);
        setScouting(false);
      });
  };

  return (
    <div className="view scout-view">
      <header className="view-header">
        <h1>Smart Scout</h1>
        <p className="subtitle">Exploration engine for family flight windows</p>
      </header>

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

      <div className="scout-results-grid">
        {results.map((r, i) => {
          const dDate = new Date(r.depart_date);
          const rDate = new Date(r.return_date);
          const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
          // Normalise breakdown keys: FastAPI serialises dataclass with raw field names
          // (base_fare_adults, bag_fees) but DB stores as_dict() names (base_adults, bags).
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
                      // Map FastAPI dataclass field names → as_dict() keys used in DB
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

const Monitoring = () => {
  const [cron, setCron] = useState<any>(null);
  const [trips, setTrips] = useState<any[]>([]);
  const [stats, setStats] = useState({ total_trips: 0, active: 0, snapshots: 0 });
  const [selectedTrips, setSelectedTrips] = useState<Set<number>>(new Set());
  const [editingCronId, setEditingCronId] = useState<number | null>(null);
  const [tempCron, setTempCron] = useState("");
  const [refreshing, setRefreshing] = useState<Set<number>>(new Set());

  const fetchData = () => {
    fetch('/api/cron').then(res => res.json()).then(setCron);
    fetch('/api/trips').then(res => res.json()).then(data => {
      setTrips(data);
      const active = data.filter((t: any) => t.is_active).length;
      setStats({ 
        total_trips: data.length, 
        active, 
        snapshots: data.reduce((acc: number, t: any) => acc + (t.snapshots_count || 10), 0) 
      });
    });
  };

  useEffect(() => {
    fetchData();
  }, []);

  const toggleTrip = (id: number) => {
    fetch(`/api/trips/${id}/toggle`, { method: 'POST' }).then(() => fetchData());
  };

  const refreshTrip = (id: number) => {
    setRefreshing(prev => new Set(prev).add(id));
    fetch(`/api/trips/${id}/refresh`, { method: 'POST' })
      .then(() => {
        setRefreshing(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        fetchData();
      });
  };

  const handleBulkRefresh = () => {
    const promises = Array.from(selectedTrips).map(id => {
      setRefreshing(prev => new Set(prev).add(id));
      return fetch(`/api/trips/${id}/refresh`, { method: 'POST' });
    });
    Promise.all(promises).then(() => {
      setRefreshing(new Set());
      fetchData();
    });
  };

  const startEditingCron = (trip: any) => {
    setEditingCronId(trip.id);
    setTempCron(trip.cron_schedule || "0 7 * * *");
  };

  const saveCron = (id: number) => {
    fetch(`/api/trips/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cron_schedule: tempCron })
    }).then(() => {
      setEditingCronId(null);
      fetchData();
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedTrips(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedTrips.size === trips.length) setSelectedTrips(new Set());
    else setSelectedTrips(new Set(trips.map(t => t.id)));
  };

  const getNextRun = (tripId: number) => {
    const job = cron?.jobs?.find((j: any) => j.id === `poll_trip_${tripId}`);
    return job?.next_run;
  };

  return (
    <div className="view monitoring-view">
      <header className="view-header">
        <h1>Monitoring</h1>
        <p className="subtitle">System health and automated polling status</p>
      </header>

      <div className="stats-dashboard">
        <div className="stat-pill glass">
          <Activity className="p-icon blue" />
          <div className="p-info">
            <span className="p-val">{stats.active} / {stats.total_trips}</span>
            <span className="p-label">Active Trips</span>
          </div>
        </div>
        <div className="stat-pill glass">
          <Clock className="p-icon green" />
          <div className="p-info">
            <span className="p-val">{cron?.active ? "Scheduled" : "Off"}</span>
            <span className="p-label">Automated Check</span>
          </div>
        </div>
        <div className="stat-pill glass">
          <CalendarDays className="p-icon purple" />
          <div className="p-info">
            <span className="p-val">2026-03</span>
            <span className="p-label">Holiday Data</span>
          </div>
        </div>
      </div>

      <div className="monitoring-details glass">
        <div className="mon-table-header">
          <h3>Managed Trips</h3>
          <div className="mon-table-actions">
            {selectedTrips.size > 0 && (
              <button className="btn btn-primary btn-sm" onClick={handleBulkRefresh}>
                <RefreshCcw size={14} className={refreshing.size > 0 ? "spin" : ""} /> Refresh Selected ({selectedTrips.size})
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => fetch('/api/cron', {method: 'POST'}).then(() => fetchData())}>
              Sync Scheduler
            </button>
          </div>
        </div>

        <table className="monitoring-table">
          <thead>
            <tr>
              <th style={{ width: '40px' }}>
                <input type="checkbox" checked={selectedTrips.size === trips.length && trips.length > 0} onChange={toggleAll} />
              </th>
              <th>Trip Details</th>
              <th>Status</th>
              <th>Schedule (Cron)</th>
              <th>Next Run</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {trips.map(trip => (
              <tr key={trip.id}>
                <td>
                  <input type="checkbox" checked={selectedTrips.has(trip.id)} onChange={() => toggleSelect(trip.id)} />
                </td>
                <td>
                  <div className="trip-cell">
                    <span className="trip-name">{trip.label}</span>
                    <span className="trip-route">{trip.origin} → {trip.destination}</span>
                  </div>
                </td>
                <td>
                  <div className="action-btns" style={{ alignItems: 'center' }}>
                    <button 
                      className={`btn-toggle ${trip.is_active ? 'on' : ''}`} 
                      onClick={() => toggleTrip(trip.id)}
                      title={trip.is_active ? "Deactivate" : "Activate"}
                    >
                      <div className="toggle-thumb" />
                    </button>
                    <span className={`status-badge ${trip.is_active ? 'active' : 'inactive'}`}>
                      {trip.is_active ? 'Polling' : 'Paused'}
                    </span>
                  </div>
                </td>
                <td>
                  {editingCronId === trip.id ? (
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <input 
                        type="text" 
                        value={tempCron} 
                        onChange={e => setTempCron(e.target.value)}
                        className="input-field"
                        style={{ padding: '4px 8px', fontSize: '0.8rem', width: '100px', margin: 0 }}
                        autoFocus
                      />
                      <button className="btn-icon" onClick={() => saveCron(trip.id)}><CheckCircle2 size={16} /></button>
                      <button className="btn-icon" onClick={() => setEditingCronId(null)}><X size={16} /></button>
                    </div>
                  ) : (
                    <div className="cron-cell" onClick={() => startEditingCron(trip)} title="Click to edit schedule">
                      {trip.cron_schedule}
                    </div>
                  )}
                </td>
                <td>
                  <span className="dim-text" style={{ fontSize: '0.8rem' }}>
                    {trip.is_active ? (getNextRun(trip.id) ? new Date(getNextRun(trip.id)).toLocaleString() : 'Pending...') : '—'}
                  </span>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button 
                    className="btn btn-ghost btn-sm" 
                    onClick={() => refreshTrip(trip.id)}
                    disabled={refreshing.has(trip.id)}
                  >
                    <RefreshCcw size={14} className={refreshing.has(trip.id) ? "spin" : ""} />
                    {refreshing.has(trip.id) ? "Polling..." : "Manual Poll"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Profile = () => {
  const [profile, setProfile] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch('/api/profile').then(res => res.json()).then(setProfile);
  }, []);

  const [recomputing, setRecomputing] = useState(false);
  const [recomputeMsg, setRecomputeMsg] = useState<string | null>(null);

  const saveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setRecomputeMsg(null);
    fetch('/api/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    }).then(() => {
      setSaving(false);
      setRecomputing(true);
      return fetch('/api/recompute', { method: 'POST' });
    }).then(res => res.json()).then(data => {
      setRecomputing(false);
      setRecomputeMsg(`Costs updated: ${data.updated_trips} trips, ${data.updated_snapshots} snapshots recomputed.`);
      window.dispatchEvent(new Event('fom:recomputed'));
    }).catch(() => {
      setRecomputing(false);
    });
  };

  if (!profile) return <div>Loading Profile...</div>;

  return (
    <div className="view profile-view">
      <header className="view-header">
        <h1>Family Profile</h1>
        <p className="subtitle">Manage default travel settings and passengers</p>
      </header>

      <form className="profile-form glass" onSubmit={saveProfile}>
        <div className="form-section">
          <h3>Family Structure</h3>
          <div className="row">
            <div className="input-group">
              <label>Adults</label>
              <input type="number" value={profile.adults} onChange={e => setProfile({...profile, adults: parseInt(e.target.value)})} className="input-field" />
            </div>
            <div className="input-group">
              <label>Origin Airport</label>
              <input type="text" value={profile.origin_airport} onChange={e => setProfile({...profile, origin_airport: e.target.value.toUpperCase()})} className="input-field" />
            </div>
          </div>
          
          <div className="children-list">
            <label>Children</label>
            {profile.children.map((c: any, i: number) => (
              <div key={i} className="child-row">
                <input type="text" value={c.name} onChange={e => {
                  const newChildren = [...profile.children];
                  newChildren[i].name = e.target.value;
                  setProfile({...profile, children: newChildren});
                }} className="input-field" placeholder="Name" />
                <input type="date" value={c.dob} onChange={e => {
                  const newChildren = [...profile.children];
                  newChildren[i].dob = e.target.value;
                  setProfile({...profile, children: newChildren});
                }} className="input-field" />
                <button type="button" className="btn-icon" onClick={() => {
                  setProfile({...profile, children: profile.children.filter((_: any, idx: number) => idx !== i)});
                }}><Trash2 size={16} /></button>
              </div>
            ))}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
              setProfile({...profile, children: [...profile.children, {name: '', dob: ''}]})
            }}><Plus size={14} /> Add Child</button>
          </div>
        </div>

        <div className="form-section">
          <h3>Regional Preferences</h3>
          <div className="row">
            <div className="input-group">
              <label>State (for Holidays)</label>
              <select value={profile.state} onChange={e => setProfile({...profile, state: e.target.value})} className="select-field">
                <option value="QLD">Queensland</option>
                <option value="NSW">New South Wales</option>
                <option value="VIC">Victoria</option>
                <option value="ACT">ACT</option>
                <option value="SA">South Australia</option>
                <option value="WA">Western Australia</option>
                <option value="TAS">Tasmania</option>
                <option value="NT">Northern Territory</option>
              </select>
            </div>
            <div className="input-group">
              <label>School Type</label>
              <select value={profile.school_type} onChange={e => setProfile({...profile, school_type: e.target.value})} className="select-field">
                <option value="state">State</option>
                <option value="independent">Independent</option>
                <option value="catholic">Catholic</option>
              </select>
            </div>
          </div>
        </div>

        <div className="form-section">
          <h3>Default Flight Preferences</h3>
          <div className="row">
            <div className="input-group">
              <label>Bags per person</label>
              <input type="number" value={profile.bags_per_person} onChange={e => setProfile({...profile, bags_per_person: parseInt(e.target.value)})} className="input-field" />
            </div>
            <div className="input-group">
              <label>Max Stops</label>
              <select value={profile.max_stops} onChange={e => setProfile({...profile, max_stops: parseInt(e.target.value)})} className="select-field">
                <option value="0">Non-stop</option>
                <option value="1">Up to 1 stop</option>
                <option value="2">Up to 2 stops</option>
              </select>
            </div>
          </div>
          <div className="row">
            <div className="input-group">
              <label>Earliest Departure (Hour)</label>
              <input type="number" min="0" max="23" value={profile.earliest_hour} onChange={e => setProfile({...profile, earliest_hour: parseInt(e.target.value)})} className="input-field" />
            </div>
            <div className="input-group">
              <label>Latest Departure (Hour)</label>
              <input type="number" min="0" max="23" value={profile.latest_hour} onChange={e => setProfile({...profile, latest_hour: parseInt(e.target.value)})} className="input-field" />
            </div>
          </div>
          <div className="row">
            <div className="input-group">
              <label>Default Trip Length (Nights)</label>
              <input type="number" value={profile.default_trip_length} onChange={e => setProfile({...profile, default_trip_length: parseInt(e.target.value)})} className="input-field" />
            </div>
            <div className="input-group">
              <label>Global Budget Threshold (AUD)</label>
              <input type="number" value={profile.budget_threshold_aud || ''} onChange={e => setProfile({...profile, budget_threshold_aud: e.target.value ? parseFloat(e.target.value) : null})} className="input-field" placeholder="No limit" />
            </div>
          </div>
          <div className="input-group">
            <label>Blocked Airlines (Comma separated IATA codes)</label>
            <input type="text" value={profile.blocked_airlines.join(', ')} onChange={e => setProfile({...profile, blocked_airlines: e.target.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s)})} className="input-field" placeholder="e.g. JQ, TR" />
          </div>
        </div>

        <button type="submit" className="btn btn-primary btn-lg" disabled={saving || recomputing}>
          {saving || recomputing ? <RefreshCcw className="animate-spin" /> : <Save />}
          <span>{saving ? 'Saving...' : recomputing ? 'Recomputing costs...' : 'Save Profile Defaults'}</span>
        </button>
        {recomputeMsg && (
          <p style={{ marginTop: '8px', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            <CheckCircle2 size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
            {recomputeMsg}
          </p>
        )}
      </form>
    </div>
  );
};

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

function App() {
  const location = useLocation();
  return (
    <div className="app-container">
      <Sidebar />
      <main className="content">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scout" element={<Scout />} />
            <Route path="/planner" element={<Planner />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  );
}

export default App;
