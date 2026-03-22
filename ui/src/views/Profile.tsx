/**
 * Family Profile view — manage default travel settings and passengers.
 */
import React, { useState, useEffect } from 'react'
import {
  RefreshCcw,
  CheckCircle2,
  Trash2,
  Save,
  Plus,
} from 'lucide-react'

const Profile = () => {
  const [profile, setProfile] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [recomputeMsg, setRecomputeMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/profile').then(res => res.json()).then(setProfile);
  }, []);

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

export default Profile;
