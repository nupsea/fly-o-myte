/**
 * Analytics view — route-specific data and price percentiles.
 */
import { useState, useEffect } from 'react'
import {
  BarChart,
  Activity,
  AlertCircle,
  TrendingUp,
  Database
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { AirportInput } from '../components/shared'

const PriceTrendline = ({ data }: { data: { week: string, avg: number, min: number }[] }) => {
  if (data.length < 2) return null;

  const width = 800;
  const height = 150;
  const padding = 40;

  const allValues = data.flatMap(d => [d.avg, d.min]);
  const minVal = Math.min(...allValues) * 0.95;
  const maxVal = Math.max(...allValues) * 1.05;
  const range = maxVal - minVal;

  const getX = (index: number) => (index / (data.length - 1)) * (width - 2 * padding) + padding;
  const getY = (val: number) => height - ((val - minVal) / range) * (height - 2 * padding) - padding;

  const avgPoints = data.map((d, i) => `${getX(i)},${getY(d.avg)}`).join(' ');
  const minPoints = data.map((d, i) => `${getX(i)},${getY(d.min)}`).join(' ');

  return (
    <div style={{ marginTop: '32px', background: 'white', padding: '24px', borderRadius: '16px', border: '1px solid #e2e8f0' }}>
      <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#1e293b', marginBottom: '24px', display: 'flex', justifyContent: 'space-between' }}>
        <span>Weekly Price Trends</span>
        <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', fontWeight: 600 }}>
          <span style={{ color: '#3b82f6' }}>● Weekly Avg</span>
          <span style={{ color: '#10b981' }}>● Best Price Seen</span>
        </div>
      </h3>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ overflow: 'visible' }}>
        {/* Grid lines */}
        {[0, 0.5, 1].map(p => {
          const y = getY(minVal + range * p);
          return (
            <g key={p}>
              <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#f1f5f9" strokeWidth="1" />
              <text x={padding - 5} y={y + 4} textAnchor="end" fontSize="10" fill="#94a3b8">${Math.round(minVal + range * p)}</text>
            </g>
          )
        })}
        
        {/* Lines */}
        <polyline fill="none" stroke="#3b82f6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" points={avgPoints} opacity="0.3" />
        <polyline fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" points={minPoints} />
        
        {/* Data points */}
        {data.map((d, i) => (
          <circle key={i} cx={getX(i)} cy={getY(d.min)} r="4" fill="white" stroke="#10b981" strokeWidth="2" />
        ))}
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px' }}>
        <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{new Date(data[0].week).toLocaleDateString()}</span>
        <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Current Week</span>
      </div>
    </div>
  );
}

const AirlineComparison = ({ data }: { data: { airline: string, avg: number, count: number }[] }) => {
  if (data.length === 0) return null;
  const maxAvg = Math.max(...data.map(d => d.avg));

  return (
    <div style={{ marginTop: '32px' }}>
      <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#1e293b', marginBottom: '16px' }}>Airline Value Comparison</h3>
      <div style={{ display: 'grid', gap: '12px' }}>
        {data.map((a, i) => (
          <div key={i} style={{ background: 'white', padding: '16px', borderRadius: '12px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '20px' }}>
            <div style={{ width: '48px', height: '48px', background: '#f8fafc', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, color: '#0f172a', fontSize: '1.1rem' }}>
              {a.airline}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <span style={{ fontSize: '0.875rem', fontWeight: 700 }}>Avg. Family Cost</span>
                <span style={{ fontSize: '0.875rem', fontWeight: 800, color: '#2563eb' }}>${a.avg.toLocaleString()}</span>
              </div>
              <div style={{ height: '8px', background: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
                <motion.div 
                  initial={{ width: 0 }} 
                  animate={{ width: `${(a.avg / maxAvg) * 100}%` }} 
                  style={{ height: '100%', background: 'linear-gradient(90deg, #3b82f6, #60a5fa)', borderRadius: '4px' }} 
                />
              </div>
              <div style={{ marginTop: '6px', fontSize: '0.7rem', color: '#94a3b8', fontWeight: 600 }}>
                Based on {a.count} samples
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const Analytics = () => {
  const [origin, setOrigin] = useState('BNE')
  const [dest, setDest] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = () => {
    if (!origin || !dest) return
    setLoading(true)
    setError(null)
    setData(null)

    fetch(`/api/analytics/${origin}/${dest}`)
      .then(async res => {
        const json = await res.json()
        if (!res.ok) throw new Error(json.detail || "Failed to fetch analytics")
        return json
      })
      .then(json => {
        setData(json)
        setLoading(false)
        if (!json) setError("Not enough data collected for this route yet. Try another destination.")
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }

  // Auto-search if populated from URL params or previous state
  useEffect(() => {
    if (origin && dest && dest.length >= 3) {
      handleSearch()
    }
  }, [])

  return (
    <div className="view analytics-view">
      <header className="view-header" style={{
        marginBottom: '48px',
        padding: '32px 40px',
        background: 'linear-gradient(135deg, rgba(255,255,255,0.95), rgba(255,255,255,0.6))',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderRadius: '24px',
        border: '1px solid rgba(255,255,255,0.8)',
        boxShadow: '0 20px 40px -15px rgba(16,185,129,0.15), inset 0 1px 0 rgba(255,255,255,0.9)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{
          position: 'absolute', top: '-50%', left: '-10%', width: '400px', height: '400px',
          background: 'radial-gradient(circle, rgba(16,185,129,0.1) 0%, transparent 70%)',
          borderRadius: '50%', zIndex: 0
        }} />
        <div className="header-content" style={{ position: 'relative', zIndex: 1 }}>
          <h1 style={{ 
            fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.03em', 
            background: 'linear-gradient(135deg, #0f172a 0%, #10b981 100%)',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', WebkitTextFillColor: 'transparent',
            marginBottom: '8px'
          }}>Route Analytics</h1>
          <p className="subtitle" style={{ fontSize: '1.1rem', color: '#475569', maxWidth: '600px' }}>
            Explore historical pricing, percentiles, and holiday premiums to make data-driven booking decisions.
          </p>
        </div>
      </header>

      <div className="analytics-controls glass" style={{ padding: '24px', marginBottom: '32px' }}>
        <div className="search-grid" style={{ marginBottom: '16px' }}>
          <AirportInput label="From (Origin)" value={origin} onChange={setOrigin} />
          <AirportInput label="To (Destination)" value={dest} onChange={setDest} placeholder="e.g. LHR, DPS, SIN" />
        </div>
        <button className="btn btn-primary btn-lg" onClick={handleSearch} disabled={loading || !origin || !dest} style={{
          background: 'linear-gradient(135deg, #10b981, #059669)',
          boxShadow: '0 10px 25px -5px rgba(16,185,129,0.4), inset 0 1px 0 rgba(255,255,255,0.2)',
          border: 'none', color: 'white'
        }}>
          {loading ? <Activity className="animate-spin" /> : <BarChart />}
          <span>{loading ? 'Crunching numbers...' : 'Analyze Route'}</span>
        </button>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div className="error-banner glass" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }}>
            <AlertCircle size={18} />
            <span>{error}</span>
          </motion.div>
        )}

        {data && (
          <motion.div className="analytics-dashboard glass" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} style={{ padding: '32px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px', borderBottom: '1px solid rgba(0,0,0,0.05)', paddingBottom: '24px' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#1e293b', margin: 0 }}>
                {origin} → {dest}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#64748b', fontSize: '0.875rem', fontWeight: 600 }}>
                <Database size={16} />
                <span>{data.sample_count} data points analyzed</span>
              </div>
            </div>

            <div className="stats-dashboard" style={{ marginBottom: '40px' }}>
              <div className="stat-pill" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '24px' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, textTransform: 'uppercase', color: '#64748b', marginBottom: '8px' }}>Absolute Lowest Seen</div>
                <div style={{ fontSize: '2rem', fontWeight: 900, color: '#0f172a' }}>${data.min_price?.toLocaleString()}</div>
              </div>
              <div className="stat-pill" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '24px' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, textTransform: 'uppercase', color: '#64748b', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <TrendingUp size={14} /> Median Cost (P50)
                </div>
                <div style={{ fontSize: '2.5rem', fontWeight: 900, color: '#3b82f6' }}>${data.p50?.toLocaleString()}</div>
              </div>
              <div className="stat-pill" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '16px', padding: '24px' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, textTransform: 'uppercase', color: '#166534', marginBottom: '8px' }}>School Holiday Premium</div>
                <div style={{ fontSize: '2rem', fontWeight: 900, color: '#15803d' }}>
                  {data.school_holiday_premium_pct !== null && data.school_holiday_premium_pct !== undefined ? `+${data.school_holiday_premium_pct}%` : 'N/A'}
                </div>
              </div>
            </div>

            <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#1e293b', marginBottom: '16px' }}>Price Distribution</h3>
            <div className="distribution-meter" style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: '16px', padding: '32px' }}>
               <div style={{ position: 'relative', width: '100%', height: '24px', background: '#f1f5f9', borderRadius: '12px', margin: '24px 0 40px' }}>
                  {/* Min to Max bar */}
                  <div style={{ position: 'absolute', top: '50%', transform: 'translateY(-50%)', left: 0, width: '100%', height: '4px', background: '#cbd5e1' }} />
                  
                  {/* Median Marker */}
                  <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '60%', height: '100%', background: 'linear-gradient(90deg, #bfdbfe, #93c5fd)', borderRadius: '12px', border: '2px solid white' }}>
                    <div style={{ position: 'absolute', top: '-28px', left: 0, fontSize: '0.75rem', fontWeight: 700, color: '#3b82f6' }}>P25 (${data.p25})</div>
                    <div style={{ position: 'absolute', top: '100%', marginTop: '8px', left: '50%', transform: 'translateX(-50%)', fontSize: '0.85rem', fontWeight: 800, color: '#2563eb' }}>Median: ${data.p50}</div>
                    <div style={{ position: 'absolute', top: '-28px', right: 0, fontSize: '0.75rem', fontWeight: 700, color: '#3b82f6' }}>P75 (${data.p75})</div>
                  </div>
                  
                  {/* Min Marker */}
                  <div style={{ position: 'absolute', top: '-28px', left: '0%', fontSize: '0.75rem', fontWeight: 700, color: '#64748b' }}>Min (${data.min_price})</div>
                  <div style={{ position: 'absolute', top: '50%', left: '0%', transform: 'translate(-50%, -50%)', width: '12px', height: '12px', background: 'white', border: '3px solid #64748b', borderRadius: '50%' }} />

                  {/* Max Marker */}
                  <div style={{ position: 'absolute', top: '-28px', right: '0%', fontSize: '0.75rem', fontWeight: 700, color: '#64748b' }}>Max (${data.max_price})</div>
                  <div style={{ position: 'absolute', top: '50%', left: '100%', transform: 'translate(-50%, -50%)', width: '12px', height: '12px', background: 'white', border: '3px solid #64748b', borderRadius: '50%' }} />
               </div>
               
               <p style={{ fontSize: '0.875rem', color: '#475569', textAlign: 'center', margin: 0 }}>
                 50% of all recorded flights fall between <strong>${data.p25}</strong> and <strong>${data.p75}</strong> (the blue zone).
               </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
              <PriceTrendline data={data.weekly_trends || []} />
              <AirlineComparison data={data.airline_breakdown || []} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default Analytics
