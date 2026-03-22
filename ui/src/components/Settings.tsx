/**
 * Settings modal components for trips and campaigns.
 */
import { useState } from 'react'
import {
  Trash2,
  Plus,
} from 'lucide-react'
import { Modal } from './shared'

// ── Trip Settings Modal ──

export const TripSettingsModal = ({ trip, profile, onClose, onSave, onDelete }: { trip: any, profile: any, onClose: () => void, onSave: (id: number, data: any) => void, onDelete: (id: number) => void }) => {
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

// ── Campaign Settings Form ──

export const CampaignSettingsForm = ({ campaign, onSave, onDelete }: { campaign: any; onSave: (data: any) => void; onDelete: () => void }) => {
  const [formData, setFormData] = useState({
    name: campaign.name,
    budget_target_aud: campaign.budget_target_aud,
    notes: campaign.notes || '',
    cron_schedule: campaign.cron_schedule,
  });

  return (
    <div className="settings-form">
      <div className="input-group">
        <label>Campaign Name</label>
        <input type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="input-field" />
      </div>
      <div className="input-group">
        <label>Budget Target (AUD)</label>
        <input
          type="number"
          value={formData.budget_target_aud || ''}
          onChange={e => setFormData({...formData, budget_target_aud: e.target.value ? parseFloat(e.target.value) : null})}
          className="input-field"
          placeholder="No limit"
        />
      </div>
      <div className="input-group">
        <label>Notes</label>
        <input type="text" value={formData.notes} onChange={e => setFormData({...formData, notes: e.target.value})} className="input-field" placeholder="Free text notes..." />
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
        <button className="btn btn-danger" onClick={onDelete}>Cancel Campaign</button>
        <button className="btn btn-primary" onClick={() => onSave(formData)}>Save Changes</button>
      </div>
    </div>
  );
};
