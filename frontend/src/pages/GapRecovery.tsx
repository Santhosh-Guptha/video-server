import { useState, useEffect } from 'react'
import type { Camera } from '../types'
import { Database, Search, RefreshCw, Clock, CheckCircle } from 'lucide-react'

type GapChunk = {
  start_ts: number
  end_ts: number
  duration: number
  formatted_start: string
  formatted_end: string
}

type RecoveredStats = {
  total_count: number
  total_duration: number
  by_stream: Record<string, { count: number; duration: number }>
  recent: Array<{
    id: number
    stream_id: string
    filename: string
    start_ts: number
    end_ts: number
    duration: number
    created_at: string
  }>
}

type GapRecoveryProps = {
  cameras: Camera[]
}

export function GapRecovery({ cameras }: GapRecoveryProps) {
  const [selectedCamera, setSelectedCamera] = useState<Camera | null>(null)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  
  const [gaps, setGaps] = useState<GapChunk[]>([])
  const [selectedGaps, setSelectedGaps] = useState<Set<number>>(new Set())
  const [isScanning, setIsScanning] = useState(false)
  const [isRecovering, setIsRecovering] = useState(false)
  const [scanMessage, setScanMessage] = useState('')
  const [recoveryStatus, setRecoveryStatus] = useState('')
  
  const [stats, setStats] = useState<RecoveredStats | null>(null)
  const [isStatsLoading, setIsStatsLoading] = useState(false)

  // Initialize time fields to last 24 hours
  useEffect(() => {
    const end = new Date()
    const start = new Date(end.getTime() - 24 * 3600 * 1000)
    
    // Format to YYYY-MM-DDTHH:MM
    const formatDateTime = (d: Date) => {
      const pad = (n: number) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    }
    
    setStartTime(formatDateTime(start))
    setEndTime(formatDateTime(end))
    fetchStats()
  }, [])

  // Auto select first camera
  useEffect(() => {
    if (cameras.length > 0 && !selectedCamera) {
      setSelectedCamera(cameras[0])
    }
  }, [cameras, selectedCamera])

  const fetchStats = async () => {
    setIsStatsLoading(true)
    try {
      const res = await fetch('/api/recordings/recovered-stats')
      if (res.ok) {
        const data = await res.json()
        setStats(data)
      }
    } catch (e) {
      console.error('Failed to fetch recovered stats', e)
    } finally {
      setIsStatsLoading(false)
    }
  }

  const handleScan = async () => {
    if (!selectedCamera) return
    setIsScanning(true)
    setScanMessage('Scanning recording segments for gaps...')
    setGaps([])
    setSelectedGaps(new Set())
    
    try {
      const startEpoch = new Date(startTime).getTime() / 1000
      const endEpoch = new Date(endTime).getTime() / 1000
      
      const res = await fetch(
        `/api/recordings/${encodeURIComponent(selectedCamera.stream_id)}/gaps?start_time=${startEpoch}&end_time=${endEpoch}`
      )
      
      if (res.ok) {
        const data = (await res.json()) as GapChunk[]
        setGaps(data)
        setScanMessage(data.length === 0 ? 'No gaps found in the selected time range.' : `Scan complete! Found ${data.length} missing segments.`)
      } else {
        setScanMessage('Failed to scan gaps. Backend returned an error.')
      }
    } catch (e) {
      console.error(e)
      setScanMessage('Failed to connect to backend for gap scanning.')
    } finally {
      setIsScanning(false)
    }
  }

  const handleToggleSelectAll = () => {
    if (selectedGaps.size === gaps.length) {
      setSelectedGaps(new Set())
    } else {
      setSelectedGaps(new Set(gaps.map((_, idx) => idx)))
    }
  }

  const handleToggleSelect = (idx: number) => {
    const next = new Set(selectedGaps)
    if (next.has(idx)) {
      next.delete(idx)
    } else {
      next.add(idx)
    }
    setSelectedGaps(next)
  }

  const handleRecover = async (all = false) => {
    if (!selectedCamera) return
    const targets = all ? gaps : gaps.filter((_, idx) => selectedGaps.has(idx))
    if (targets.length === 0) return
    
    setIsRecovering(true)
    setRecoveryStatus(`Queueing ${targets.length} segments for recovery...`)
    
    try {
      const res = await fetch(`/api/recordings/${encodeURIComponent(selectedCamera.stream_id)}/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(targets.map(t => ({ start_ts: t.start_ts, end_ts: t.end_ts })))
      })
      
      if (res.ok) {
        setRecoveryStatus(`Successfully queued ${targets.length} segments. Check terminal/stats for download progress.`)
        // Clear list after successful recovery call
        setGaps([])
        setSelectedGaps(new Set())
        setTimeout(() => {
          fetchStats()
          setRecoveryStatus('')
        }, 3000)
      } else {
        setRecoveryStatus('Failed to trigger recovery. Backend returned an error.')
      }
    } catch (e) {
      console.error(e)
      setRecoveryStatus('Failed to connect to backend to trigger recovery.')
    } finally {
      setIsRecovering(false)
    }
  }

  const formatDuration = (sec: number) => {
    if (sec < 60) return `${sec.toFixed(0)}s`
    const min = sec / 60
    if (min < 60) return `${min.toFixed(1)}m`
    const hrs = min / 60
    return `${hrs.toFixed(1)}h`
  }

  return (
    <div className="gapRecoveryContainer" style={{ display: 'flex', flexDirection: 'column', gap: '24px', padding: '4px' }}>
      
      {/* Top Banner */}
      <div className="dashboardHeader" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 className="vmsModalTitle" style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0, color: '#f8fafc' }}>
            <Database size={22} className="colorBlue" style={{ color: '#3b82f6' }} /> Recording Gap Recovery Console
          </h2>
          <span className="vmsModalSubtitle" style={{ fontSize: '0.8rem', color: '#64748b' }}>Identify and recover missing recording segments from camera storage (Edge Sync)</span>
        </div>
        <button className="batchBtn" onClick={fetchStats} disabled={isStatsLoading} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <RefreshCw size={14} className={isStatsLoading ? 'spin' : ''} /> Refresh Stats
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        
        {/* Left Side: Scan & Recovery Interface */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Scan Filters Card */}
          <div style={{ background: 'rgba(30, 41, 59, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '16px', padding: '20px' }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px', marginTop: 0 }}>
              <Search size={14} /> Scan Configuration
            </h3>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Select Camera</label>
                <select 
                  className="vms-select"
                  value={selectedCamera?.id || ''}
                  onChange={(e) => {
                    const id = e.target.value
                    setSelectedCamera(cameras.find(c => c.id === id) || null)
                  }}
                >
                  {cameras.map(c => (
                    <option key={c.id} value={c.id}>{c.name} ({c.stream_id})</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Start Time</label>
                <input 
                  type="datetime-local" 
                  className="vms-input"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>End Time</label>
                <input 
                  type="datetime-local" 
                  className="vms-input"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                />
              </div>
            </div>

            <button 
              className="batchBtn" 
              onClick={handleScan}
              disabled={isScanning || !selectedCamera}
              style={{
                marginTop: '20px',
                width: '100%',
                background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                color: '#fff',
                border: 'none',
                padding: '10px',
                fontWeight: 600,
                borderRadius: '8px',
                cursor: 'pointer'
              }}
            >
              {isScanning ? 'Scanning...' : 'Scan Gaps'}
            </button>

            {scanMessage && (
              <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '12px', textAlign: 'center' }}>
                {scanMessage}
              </div>
            )}
          </div>

          {/* Gaps List Table Card */}
          {gaps.length > 0 && (
            <div style={{ background: 'rgba(30, 41, 59, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '16px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
                  <Clock size={14} /> Missing Segments Found ({gaps.length})
                </h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button 
                    className="batchBtn" 
                    onClick={handleToggleSelectAll}
                    style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                  >
                    {selectedGaps.size === gaps.length ? 'Deselect All' : 'Select All'}
                  </button>
                  <button 
                    className="batchBtn start"
                    onClick={() => handleRecover(false)}
                    disabled={selectedGaps.size === 0 || isRecovering}
                    style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                  >
                    Recover Selected ({selectedGaps.size})
                  </button>
                  <button 
                    className="batchBtn start"
                    onClick={() => handleRecover(true)}
                    disabled={isRecovering}
                    style={{ fontSize: '0.75rem', padding: '4px 10px', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', borderColor: 'rgba(16, 185, 129, 0.3)' }}
                  >
                    Recover All
                  </button>
                </div>
              </div>

              {recoveryStatus && (
                <div style={{ fontSize: '0.8rem', color: '#10b981', padding: '8px 12px', background: 'rgba(16, 185, 129, 0.1)', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                  {recoveryStatus}
                </div>
              )}

              {/* Table */}
              <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '8px' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ background: 'rgba(15, 23, 42, 0.6)', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <th style={{ padding: '10px', width: '40px' }}></th>
                      <th style={{ padding: '10px' }}>Start Time</th>
                      <th style={{ padding: '10px' }}>End Time</th>
                      <th style={{ padding: '10px' }}>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gaps.map((gap, idx) => {
                      const isChecked = selectedGaps.has(idx)
                      return (
                        <tr 
                          key={idx} 
                          onClick={() => handleToggleSelect(idx)}
                          style={{ 
                            borderBottom: '1px solid rgba(255, 255, 255, 0.03)', 
                            background: isChecked ? 'rgba(59, 130, 246, 0.05)' : 'transparent',
                            cursor: 'pointer'
                          }}
                          className="vmsSelectorItem"
                        >
                          <td style={{ padding: '10px', textAlign: 'center' }}>
                            <input 
                              type="checkbox" 
                              checked={isChecked}
                              onChange={() => {}} // click handler on TR handles it
                              style={{ cursor: 'pointer' }}
                            />
                          </td>
                          <td style={{ padding: '10px', color: '#cbd5e1' }}>{gap.formatted_start}</td>
                          <td style={{ padding: '10px', color: '#cbd5e1' }}>{gap.formatted_end}</td>
                          <td style={{ padding: '10px', fontWeight: 600, color: '#38bdf8' }}>{formatDuration(gap.duration)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>

        {/* Right Side: Recovery Statistics Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Stats Overview */}
          <div style={{ background: 'rgba(30, 41, 59, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '16px', padding: '20px' }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px', marginTop: 0 }}>
              <CheckCircle size={14} className="colorGreen" style={{ color: '#10b981' }} /> Recovery Statistics
            </h3>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Total Recovered Segments</span>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{stats?.total_count || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Total Recovered Duration</span>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#10b981' }}>
                  {stats ? formatDuration(stats.total_duration) : '0s'}
                </span>
              </div>
            </div>
          </div>

          {/* Recent Recovered Files List */}
          <div style={{ background: 'rgba(30, 41, 59, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '16px', padding: '20px' }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px', marginTop: 0 }}>
              <Clock size={14} /> Recent Recoveries
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '350px', overflowY: 'auto' }}>
              {stats?.recent && stats.recent.map((rec) => (
                <div 
                  key={rec.id} 
                  style={{ 
                    padding: '8px 12px', 
                    background: 'rgba(15, 23, 42, 0.4)', 
                    border: '1px solid rgba(255, 255, 255, 0.03)', 
                    borderRadius: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}
                >
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#60a5fa', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {rec.stream_id}
                  </span>
                  <span style={{ fontSize: '0.68rem', color: '#64748b', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {rec.filename}
                  </span>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: '#94a3b8', marginTop: '2px' }}>
                    <span>Duration: {formatDuration(rec.duration)}</span>
                    <span>{new Date(rec.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
              {(!stats?.recent || stats.recent.length === 0) && (
                <div style={{ padding: '20px 0', textAlign: 'center', fontSize: '0.75rem', color: '#64748b' }}>
                  No recovered segments found yet
                </div>
              )}
            </div>
          </div>

        </div>

      </div>

    </div>
  )
}
