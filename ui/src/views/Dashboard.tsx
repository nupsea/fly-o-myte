/**
 * Campaign-first Dashboard view.
 * Shows campaigns as the primary unit, with their active variant, recommendation, and cross-variant history.
 */
import { useState, useEffect } from 'react'
import {
  ChevronRight,
  TrendingDown,
  Clock,
  RefreshCcw,
  CalendarDays,
  Settings,
  AlertCircle,
  ArrowRight,
  Plane,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Modal, JourneyDetails, cronToHuman } from '../components/shared'
import { TripSettingsModal, CampaignSettingsForm } from '../components/Settings'

const Dashboard = () => {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrip, setSelectedTrip] = useState<any>(null);
  const [detailsCampaign, setDetailsCampaign] = useState<any>(null);
  const [campaignHistory, setCampaignHistory] = useState<any[]>([]);
  const [campaignVariants, setCampaignVariants] = useState<any[]>([]);
  const [flexTrip, setFlexTrip] = useState<any>(null);
  const [flexResults, setFlexResults] = useState<any[]>([]);
  const [flexLoading, setFlexLoading] = useState(false);
  const [flexError, setFlexError] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [editingCampaign, setEditingCampaign] = useState<any>(null);
  const [pollingAll, setPollingAll] = useState(false);
  const [refreshingTrips, setRefreshingTrips] = useState<Set<number>>(new Set());

  const fetchCampaigns = () => {
    setLoading(true);
    fetch('/api/campaigns')
      .then(res => res.json())
      .then(data => {
        setCampaigns(data);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchCampaigns();
    fetch('/api/profile').then(res => res.json()).then(setProfile);
    const handler = () => fetchCampaigns();
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

  const openCampaignDetails = (campaign: any) => {
    setDetailsCampaign(campaign);
    fetch(`/api/campaigns/${campaign.id}/history`)
      .then(res => res.json())
      .then(data => setCampaignHistory(data));
    fetch(`/api/campaigns/${campaign.id}`)
      .then(res => res.json())
      .then(data => setCampaignVariants(data.variants || []));
  };

  const handleRefresh = (tid: number) => {
    setRefreshingTrips(prev => new Set(prev).add(tid));
    fetch(`/api/trips/${tid}/refresh`, { method: 'POST' })
      .then(() => fetchCampaigns())
      .finally(() => setRefreshingTrips(prev => { const next = new Set(prev); next.delete(tid); return next; }));
  };

  const handlePollAll = () => {
    setPollingAll(true);
    fetch('/api/poll', { method: 'POST' })
      .then(() => fetchCampaigns())
      .finally(() => setPollingAll(false));
  };

  const handleDeleteCampaign = (cid: number) => {
    if (confirm("Cancel this campaign? All variant history will be preserved.")) {
      fetch(`/api/campaigns/${cid}`, { method: 'DELETE' }).then(() => fetchCampaigns());
    }
  };

  const handleDelete = (tid: number) => {
    if (confirm("Delete this trip?")) {
      fetch(`/api/trips/${tid}`, { method: 'DELETE' }).then(() => fetchCampaigns());
    }
  };

  const updateTrip = (tid: number, data: any) => {
    fetch(`/api/trips/${tid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(() => { fetchCampaigns(); setSelectedTrip(null); });
  };

  const updateCampaign = (cid: number, data: any) => {
    fetch(`/api/campaigns/${cid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(() => { fetchCampaigns(); setEditingCampaign(null); });
  };

  return (
    <div className="view dashboard-view">
      <header className="view-header" style={{
        marginBottom: '48px',
        padding: '32px 40px',
        background: 'linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255,255,255,0.4))',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderRadius: '24px',
        border: '1px solid rgba(255,255,255,0.8)',
        boxShadow: '0 20px 40px -15px rgba(37,99,235,0.1), inset 0 1px 0 rgba(255,255,255,0.9)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{
          position: 'absolute', top: '-50%', right: '-10%', width: '400px', height: '400px',
          background: 'radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)',
          borderRadius: '50%', zIndex: 0
        }} />
        <div className="header-content" style={{ position: 'relative', zIndex: 1 }}>
          <h1 style={{ 
            fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.03em', 
            background: 'linear-gradient(135deg, #0f172a 0%, #3b82f6 100%)',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', WebkitTextFillColor: 'transparent',
            marginBottom: '8px'
          }}>Flight Watch</h1>
          <p className="subtitle" style={{ fontSize: '1.1rem', color: '#475569', maxWidth: '600px' }}>
            Tracking {campaigns.length} flight watch{campaigns.length !== 1 ? 'es' : ''} across multiple date windows. Prices polled automatically, so you never miss a drop.
          </p>
        </div>
        <div className="header-actions" style={{ position: 'relative', zIndex: 1, alignSelf: 'center' }}>
          <button className="btn btn-primary" disabled={pollingAll} style={{
            padding: '12px 24px', fontSize: '1rem', borderRadius: '14px',
            background: pollingAll ? 'linear-gradient(135deg, #93c5fd, #60a5fa)' : 'linear-gradient(135deg, #3b82f6, #2563eb)',
            boxShadow: '0 10px 25px -5px rgba(37,99,235,0.4), inset 0 1px 0 rgba(255,255,255,0.2)',
            cursor: pollingAll ? 'wait' : 'pointer'
          }} onClick={handlePollAll}>
            <RefreshCcw size={18} className={pollingAll ? 'spin-icon' : ''} />
            <span>{pollingAll ? 'Polling…' : 'Poll All Data Now'}</span>
          </button>
        </div>
      </header>

      <div className="trip-grid">
        {campaigns.length === 0 && !loading && (
          <div style={{ padding: '64px', textAlign: 'center', color: '#64748b', gridColumn: '1 / -1' }}>
             <Plane size={48} style={{ opacity: 0.2, margin: '0 auto 16px' }} />
             <h3 style={{ fontSize: '1.25rem', color: '#1e293b', marginBottom: '8px' }}>No campaigns found</h3>
             <p>Use the Smart Scout to find flights and save them to a new campaign.</p>
          </div>
        )}
        {campaigns.map((campaign) => {
          const trip = campaign.active_variant;
          const rec = campaign.recommendation;
          const snap = campaign.latest_snapshot;
          const isPaused = campaign.status !== 'active' || (trip && trip.is_active === 0);

          return (
            <motion.div key={campaign.id} className={`trip-card glass ${isPaused ? 'paused-campaign' : ''}`} layoutId={`campaign-${campaign.id}`}>
              <div className="card-top">
                <div className="route">
                  <span className="iata">{campaign.origin}</span>
                  <ChevronRight size={14} />
                  <span className="iata">{campaign.destination}</span>
                </div>
                <div className="actions-top">
                   <button className="btn-icon" onClick={() => setEditingCampaign(campaign)} title="Campaign Settings"><Settings size={16} /></button>
                   <div className={`status-badge status-${rec?.decision || 'monitor'}`}>
                     {rec?.decision?.replace('_', ' ') || 'monitoring'}
                   </div>
                </div>
              </div>

              {/* Campaign name */}
              <div style={{ padding: '0 16px', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-main)' }}>{campaign.name}</span>
              </div>

              <div className="card-body">
                {trip ? (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div className="trip-dates">
                      <CalendarDays size={14} />
                      <span>{trip.depart_date}</span>
                      {trip.return_date && <span> — {trip.return_date}</span>}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Clock size={12} /> {cronToHuman(campaign.cron_schedule)}
                    </div>
                  </div>
                ) : (
                  <div style={{ marginBottom: '8px', color: 'var(--text-muted)', fontSize: '0.8125rem', fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <CalendarDays size={14} /> Dates not set (Monitoring paused)
                  </div>
                )}

                {trip && trip.depart_date && trip.return_date && (
                  <div style={{ marginBottom: '8px' }}>
                    <span className="trip-days-badge">
                      {Math.round((new Date(trip.return_date).getTime() - new Date(trip.depart_date).getTime()) / 86400000)} days
                    </span>
                  </div>
                )}

                {snap ? (
                  <>
                    <div className="flight-info-summary" style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                      <strong>{snap.airline_code}</strong> &middot; {snap.stops} stop{snap.stops !== 1 ? 's' : ''} &middot; departs {snap.departure_time}
                    </div>
                    <div className="price-display">
                      <span className="price">${snap.true_family_cost?.toLocaleString() || '---'}</span>
                      <span className="currency">AUD</span>
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                    No price data yet
                  </div>
                )}

                {/* Campaign meta badges */}
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {campaign.variant_count > 1 && (
                    <span className="campaign-meta-badge">{campaign.variant_count} variants</span>
                  )}
                  {campaign.total_snapshots > 0 && (
                    <span className="campaign-meta-badge">{campaign.total_snapshots} data pts</span>
                  )}
                  {campaign.budget_target_aud && (
                    <span className="campaign-meta-badge">Budget: ${campaign.budget_target_aud.toLocaleString()}</span>
                  )}
                </div>

                {rec && (
                  <div className="savings-meter">
                    <div className="meter-label">
                      <span>{rec.price_level_signal} Price Level</span>
                      <span className="savings-value">
                        {rec.trend_slope < 0 ? <TrendingDown size={12} /> : null}
                        {Math.abs(rec.trend_slope).toFixed(0)} AUD/day
                      </span>
                    </div>
                    <div className="meter-track">
                      <div className="meter-fill" style={{ width: `${Math.min(100, (rec.confidence * 100))}%` }} />
                    </div>
                  </div>
                )}
              </div>

              <div className="card-footer">
                <button className="btn btn-ghost btn-sm" onClick={() => openCampaignDetails(campaign)}>Details & History</button>
                {trip && <button className="btn btn-light btn-sm" onClick={() => openFlex(trip)}>Find Better Dates</button>}
                {trip && <button className="btn btn-icon btn-sm" disabled={refreshingTrips.has(trip.id)} onClick={() => handleRefresh(trip.id)} title="Manual Refresh"><RefreshCcw size={14} className={refreshingTrips.has(trip.id) ? 'spin-icon' : ''} /></button>}
              </div>
            </motion.div>
          );
        })}
      </div>

      <AnimatePresence>
        {detailsCampaign && (
          <Modal wide title={`Campaign: ${detailsCampaign.name}`} onClose={() => setDetailsCampaign(null)}>
            <div className="details-content">
              <div className="details-header">
                <div className="dh-left">
                  <h3>{detailsCampaign.origin} → {detailsCampaign.destination}</h3>
                  <p className="dim-text">
                    {detailsCampaign.total_snapshots} data points across {detailsCampaign.variant_count} variant{detailsCampaign.variant_count !== 1 ? 's' : ''}
                  </p>
                </div>
                <div className="dh-right">
                  <span className="dh-price">${detailsCampaign.latest_snapshot?.true_family_cost?.toLocaleString() || '---'}</span>
                </div>
              </div>

              {/* Variant Timeline */}
              {campaignVariants.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <h3 style={{ marginBottom: '12px' }}>Date Variants</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {campaignVariants.map((v: any) => (
                      <div key={v.id} className={`variant-row glass ${v.is_archived ? 'archived' : 'active'}`}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1 }}>
                          <span className={`variant-status-dot ${v.is_archived ? 'dot-archived' : 'dot-active'}`} />
                          <div>
                            <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{v.depart_date}</span>
                            {v.return_date && <span style={{ color: 'var(--text-muted)' }}> — {v.return_date}</span>}
                          </div>
                          {v.is_archived ? (
                            <span className="variant-badge archived-badge">archived</span>
                          ) : (
                            <span className="variant-badge active-badge">active</span>
                          )}
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {new Date(v.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Active variant breakdown */}
              {detailsCampaign.active_variant && detailsCampaign.latest_snapshot && (
                <>
                  <h3>Active Variant — True Cost Breakdown</h3>
                  <div className="price-breakdown">
                    {(() => {
                      try {
                        const bd = JSON.parse(detailsCampaign.latest_snapshot?.true_cost_breakdown || '{}');
                        return (
                          <ul className="bd-list">
                            <li><span>Base Fares:</span> <span>${(bd.base_adults || 0) + (bd.base_children || 0)}</span></li>
                            <li><span>Bags:</span> <span>${bd.bags || 0}</span></li>
                            <li><span>Seat Selection:</span> <span>${bd.seats || 0}</span></li>
                            <li><span>Infant Fees:</span> <span>${bd.infant || 0}</span></li>
                          </ul>
                        );
                      } catch { return <p>No breakdown available.</p>; }
                    })()}
                  </div>

                  <JourneyDetails snapshot={detailsCampaign.latest_snapshot} returnDate={detailsCampaign.active_variant?.return_date} />
                </>
              )}

              {/* Cross-variant price history */}
              <div className="history-section">
                <h3>Price History (All Variants)</h3>
                {campaignHistory.length === 0 ? <p className="dim-text">Loading history...</p> : (
                  <div className="history-list">
                    {Object.entries(
                      campaignHistory.reduce((acc: any, snap: any) => {
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
                          {(() => {
                            const seen = new Set();
                            return snaps
                              .sort((a: any, b: any) => a.true_family_cost - b.true_family_cost)
                              .filter((snap: any) => {
                                 const key = `${snap.rank}-${snap.true_family_cost}-${snap.airline_code}-${snap.departure_time}`;
                                 if (seen.has(key)) return false;
                                 seen.add(key);
                                 return true;
                              })
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
                          });
                          })()}
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

        {editingCampaign && (
          <Modal title={`Campaign: ${editingCampaign.name}`} onClose={() => setEditingCampaign(null)}>
            <CampaignSettingsForm
              campaign={editingCampaign}
              onSave={(data: any) => updateCampaign(editingCampaign.id, data)}
              onDelete={() => handleDeleteCampaign(editingCampaign.id)}
            />
          </Modal>
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
                                fetchCampaigns();
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
        )}
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;
