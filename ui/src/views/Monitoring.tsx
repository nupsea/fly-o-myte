/**
 * Monitoring view — system health and automated polling status.
 */
import { useState, useEffect } from 'react'
import {
  Activity,
  Clock,
  RefreshCcw,
  CalendarDays,
  CheckCircle2,
  X,
} from 'lucide-react'

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

export default Monitoring;
