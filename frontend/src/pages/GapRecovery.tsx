import { useState, useEffect, useMemo, useRef } from 'react'
import type { Camera } from '../types'
import { Database, Search, RefreshCw, Clock, CheckCircle, ChevronDown, Calendar, Download, Loader2 } from 'lucide-react'

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
  const [selectedStreamId, setSelectedStreamId] = useState<string>('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')

  useEffect(() => {
    if (selectedCamera) {
      const matched = selectedCamera.streams.find(s => s.stream_id === selectedCamera.stream_id)
      if (matched) {
        setSelectedStreamId(matched.stream_id)
      } else if (selectedCamera.streams.length > 0) {
        setSelectedStreamId(selectedCamera.streams[0].stream_id)
      } else {
        setSelectedStreamId(selectedCamera.stream_id)
      }
    } else {
      setSelectedStreamId('')
    }
  }, [selectedCamera])
  
  const [gaps, setGaps] = useState<GapChunk[]>([])
  const [selectedGaps, setSelectedGaps] = useState<Set<number>>(new Set())
  const [isScanning, setIsScanning] = useState(false)
  const [isRecovering, setIsRecovering] = useState(false)
  const [scanMessage, setScanMessage] = useState('')
  const [recoveryStatus, setRecoveryStatus] = useState('')
  
  const [stats, setStats] = useState<RecoveredStats | null>(null)
  const [isStatsLoading, setIsStatsLoading] = useState(false)

  // On-demand SD card download states
  const [isOnDemandDownloading, setIsOnDemandDownloading] = useState(false)
  const [onDemandError, setOnDemandError] = useState<string | null>(null)
  const [onDemandStatus, setOnDemandStatus] = useState<string | null>(null)

  // Searchable dropdown states
  const [searchQuery, setSearchQuery] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const handleOnDemandDownload = async () => {
    if (!selectedCamera) return
    setIsOnDemandDownloading(true)
    setOnDemandError(null)
    setOnDemandStatus('Preparing stream... Your download will begin shortly.')
    
    try {
      const start_ts = new Date(startTime).getTime() / 1000
      const end_ts = new Date(endTime).getTime() / 1000
      
      let downloadUrl = `/api/recordings/sd-card/download?stream_id=${encodeURIComponent(selectedStreamId)}&start_ts=${start_ts}&end_ts=${end_ts}`
      
      // Bypass Vite dev proxy in development to avoid socket timeouts
      if (window.location.port === '5173') {
        downloadUrl = `http://${window.location.hostname}:8005${downloadUrl}`
      }
      
      // Trigger native browser download directly on the streaming endpoint
      const link = document.createElement('a')
      link.href = downloadUrl
      link.setAttribute('download', '')
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      
      setOnDemandStatus('Download started! Real-time download progress is active in your browser.')
      setTimeout(() => setOnDemandStatus(null), 8000)
    } catch (e: any) {
      console.error(e)
      setOnDemandError(e.message || 'An error occurred during SD card download.')
      setOnDemandStatus(null)
    } finally {
      setIsOnDemandDownloading(false)
    }
  }

  // Initialize time fields to last 24 hours
  useEffect(() => {
    resetTimeRange()
    fetchStats()
  }, [])

  const setPresetHours = (hours: number) => {
    const end = new Date()
    const start = new Date(end.getTime() - hours * 3600 * 1000)
    
    const formatDateTime = (d: Date) => {
      const pad = (n: number) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    }
    
    setStartTime(formatDateTime(start))
    setEndTime(formatDateTime(end))
  }

  const resetTimeRange = () => {
    setPresetHours(24)
  }

  // Close searchable dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // Auto select first camera
  useEffect(() => {
    if (cameras.length > 0 && !selectedCamera) {
      setSelectedCamera(cameras[0])
    }
  }, [cameras, selectedCamera])

  // Filtered cameras based on search query
  const filteredCameras = useMemo(() => {
    if (!searchQuery.trim()) return cameras
    const q = searchQuery.toLowerCase()
    return cameras.filter(c => 
      c.name.toLowerCase().includes(q) || 
      c.stream_id.toLowerCase().includes(q)
    )
  }, [cameras, searchQuery])

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
        `/api/recordings/${encodeURIComponent(selectedStreamId)}/gaps?start_time=${startEpoch}&end_time=${endEpoch}`
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
      const res = await fetch(`/api/recordings/${encodeURIComponent(selectedStreamId)}/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(targets.map(t => ({ start_ts: t.start_ts, end_ts: t.end_ts })))
      })
      
      if (res.ok) {
        setRecoveryStatus(`Successfully queued ${targets.length} segments. Check terminal/stats for download progress.`)
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
                <Search size={14} /> Scan Configuration
              </h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Presets:</span>
                <button 
                  onClick={() => setPresetHours(1)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#60a5fa',
                    fontSize: '0.72rem',
                    cursor: 'pointer',
                    padding: 0
                  }}
                >
                  Last 1h
                </button>
                <span style={{ fontSize: '0.72rem', color: '#334155' }}>|</span>
                <button 
                  onClick={() => setPresetHours(2)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#60a5fa',
                    fontSize: '0.72rem',
                    cursor: 'pointer',
                    padding: 0
                  }}
                >
                  Last 2h
                </button>
                <span style={{ fontSize: '0.72rem', color: '#334155' }}>|</span>
                <button 
                  onClick={() => setPresetHours(24)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#60a5fa',
                    fontSize: '0.72rem',
                    cursor: 'pointer',
                    padding: 0,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <Calendar size={12} /> Last 24h
                </button>
              </div>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1fr 1fr', gap: '16px' }}>
              {/* Searchable Dropdown Selector */}
              <div ref={dropdownRef} style={{ position: 'relative' }}>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '8px' }}>Select Camera</label>
                <div 
                  onClick={() => setDropdownOpen(!dropdownOpen)}
                  style={{
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 12px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    color: '#f8fafc',
                    fontSize: '0.85rem',
                    minHeight: '38px',
                    boxSizing: 'border-box'
                  }}
                >
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '85%' }}>
                    {selectedCamera ? `${selectedCamera.name} (${selectedCamera.stream_id})` : 'Select a camera...'}
                  </span>
                  <ChevronDown size={16} style={{ color: '#64748b', transform: dropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', marginLeft: '6px', flexShrink: 0 }} />
                </div>
                
                {dropdownOpen && (
                  <div 
                    style={{
                      position: 'absolute',
                      top: '100%',
                      left: 0,
                      right: 0,
                      marginTop: '4px',
                      background: '#1e293b',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      borderRadius: '8px',
                      boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.7), 0 8px 10px -6px rgba(0, 0, 0, 0.7)',
                      zIndex: 1000,
                      padding: '8px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(15, 23, 42, 0.6)', borderRadius: '6px', padding: '4px 8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <Search size={14} style={{ color: '#94a3b8', marginRight: '6px', flexShrink: 0 }} />
                      <input
                        type="text"
                        placeholder="Search by name or stream ID..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onClick={(e) => e.stopPropagation()} 
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#f8fafc',
                          fontSize: '0.8rem',
                          outline: 'none',
                          width: '100%',
                          padding: '4px 0'
                        }}
                      />
                    </div>
                    <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      {filteredCameras.map(c => (
                        <div
                          key={c.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedCamera(c);
                            setDropdownOpen(false);
                            setSearchQuery('');
                          }}
                          style={{
                            padding: '8px 10px',
                            borderRadius: '6px',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                            background: selectedCamera?.id === c.id ? 'rgba(59, 130, 246, 0.25)' : 'transparent',
                            color: selectedCamera?.id === c.id ? '#60a5fa' : '#cbd5e1',
                            transition: 'all 0.15s',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                          }}
                          onMouseEnter={(e) => {
                            if (selectedCamera?.id !== c.id) {
                              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (selectedCamera?.id !== c.id) {
                              e.currentTarget.style.background = 'transparent'
                            }
                          }}
                        >
                          <span style={{ fontWeight: selectedCamera?.id === c.id ? 600 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                            {c.name}
                          </span>
                          <span style={{ fontSize: '0.7rem', color: '#64748b', fontFamily: 'monospace' }}>{c.stream_id}</span>
                        </div>
                      ))}
                      {filteredCameras.length === 0 && (
                        <div style={{ padding: '12px', fontSize: '0.75rem', color: '#64748b', textAlign: 'center' }}>
                          No cameras found
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Stream Profile Selector */}
              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '8px' }}>Select Stream</label>
                <select
                  value={selectedStreamId}
                  onChange={(e) => setSelectedStreamId(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    color: '#f8fafc',
                    padding: '8px 12px',
                    fontSize: '0.85rem',
                    minHeight: '38px',
                    boxSizing: 'border-box',
                    outline: 'none',
                    cursor: 'pointer'
                  }}
                >
                  {selectedCamera?.streams?.map((s) => (
                    <option key={s.stream_id} value={s.stream_id} style={{ background: '#1e293b', color: '#f8fafc' }}>
                      {s.profile_type} ({s.stream_id.split('_').pop() || s.stream_id})
                    </option>
                  )) || (
                    <option value={selectedStreamId}>{selectedStreamId}</option>
                  )}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '8px' }}>Start Time</label>
                <input 
                  type="datetime-local" 
                  className="vms-input"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    color: '#f8fafc',
                    padding: '8px 12px',
                    fontSize: '0.85rem',
                    minHeight: '38px',
                    boxSizing: 'border-box',
                    outline: 'none'
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '8px' }}>End Time</label>
                <input 
                  type="datetime-local" 
                  className="vms-input"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    color: '#f8fafc',
                    padding: '8px 12px',
                    fontSize: '0.85rem',
                    minHeight: '38px',
                    boxSizing: 'border-box',
                    outline: 'none'
                  }}
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
                cursor: 'pointer',
                transition: 'opacity 0.2s',
                opacity: isScanning || !selectedCamera ? 0.6 : 1
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

          {/* On-Demand Download Card */}
          <div style={{ background: 'rgba(30, 41, 59, 0.2)', border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '16px', padding: '20px' }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px', margin: '0 0 12px 0' }}>
              <Download size={14} /> On-Demand SD Card Footage Download
            </h3>
            <span style={{ fontSize: '0.75rem', color: '#64748b', display: 'block', marginBottom: '16px' }}>
              Directly retrieve and download any recorded video clip from the camera's local SD card storage on-demand.
            </span>
            
            <button 
              className="batchBtn" 
              onClick={handleOnDemandDownload}
              disabled={isOnDemandDownloading || !selectedCamera}
              style={{
                width: '100%',
                background: 'linear-gradient(135deg, #10b981, #047857)',
                color: '#fff',
                border: 'none',
                padding: '10px',
                fontWeight: 600,
                borderRadius: '8px',
                cursor: 'pointer',
                transition: 'opacity 0.2s',
                opacity: isOnDemandDownloading || !selectedCamera ? 0.6 : 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px'
              }}
            >
              {isOnDemandDownloading ? (
                <>
                  <Loader2 size={16} className="spin" />
                  Downloading from Camera SD Card...
                </>
              ) : (
                <>
                  <Download size={16} />
                  Download Custom Range
                </>
              )}
            </button>

            {onDemandError && (
              <div style={{ fontSize: '0.8rem', color: '#ef4444', marginTop: '12px', textAlign: 'center' }}>
                {onDemandError}
              </div>
            )}
            {onDemandStatus && (
              <div style={{ fontSize: '0.8rem', color: '#10b981', marginTop: '12px', textAlign: 'center' }}>
                {onDemandStatus}
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
