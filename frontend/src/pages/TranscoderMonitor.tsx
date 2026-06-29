import React, { useEffect, useState } from 'react'
import { Activity, Database, Clock, Sliders, AlertTriangle, Layers, Loader2 } from 'lucide-react'
import { fetchTranscodingStatus } from '../lib/api'

interface TranscodingSession {
  stream_id: string
  pid?: number
  viewers: number
  uptime_s: number
  type: 'local' | 'remote'
  gpu_index?: number | null
}

interface TranscoderStatusData {
  timestamp: number
  local: {
    active_count: number
    sessions: TranscodingSession[]
  }
  remote: {
    workers?: {
      live_worker_count: number
      playback_worker_count: number
      live_active_sessions: Array<{
        stream_id: string
        gpu_index: number | null
        viewers: number
        uptime_s: number
      }>
      playback_active_sessions: Array<{
        session_key: string
        gpu_index: number | null
        viewers: number
        uptime_s: number
      }>
    }
    gpus?: Array<{
      index: number
      name: string
      utilization: number
      memory_free: number
    }>
  } | null
  analytics: {
    total_completed_sessions: number
    system_cpu_usage: number
    system_gpu_usage: number
  }
}

export default function TranscoderMonitor() {
  const [data, setData] = useState<TranscoderStatusData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = async () => {
    try {
      const res = await fetchTranscodingStatus()
      setData(res)
      setError(null)
    } catch (err: any) {
      setError(err.message || 'Failed to connect to transcoding metrics API')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
    const interval = setInterval(loadStatus, 4000)
    return () => clearInterval(interval)
  }, [])

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}m ${s}s`
  }

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh', gap: '16px' }}>
        <Loader2 size={36} className="animate-spin" style={{ color: '#a855f7' }} />
        <span style={{ fontSize: '0.96rem', color: '#94a3b8', fontWeight: 500 }}>Loading real-time transcoding metrics...</span>
      </div>
    )
  }

  // Compile active sessions list from both local and remote nodes
  const activeSessions: TranscodingSession[] = []
  
  if (data?.local?.sessions) {
    activeSessions.push(...data.local.sessions)
  }

  if (data?.remote?.workers?.live_active_sessions) {
    data.remote.workers.live_active_sessions.forEach(s => {
      activeSessions.push({
        stream_id: s.stream_id,
        viewers: s.viewers,
        uptime_s: s.uptime_s,
        type: 'remote',
        gpu_index: s.gpu_index
      })
    })
  }

  if (data?.remote?.workers?.playback_active_sessions) {
    data.remote.workers.playback_active_sessions.forEach(s => {
      activeSessions.push({
        stream_id: s.session_key,
        viewers: s.viewers,
        uptime_s: s.uptime_s,
        type: 'remote',
        gpu_index: s.gpu_index
      })
    })
  }

  const localCount = data?.local?.active_count || 0
  const remoteCount = (data?.remote?.workers?.live_worker_count || 0) + (data?.remote?.workers?.playback_worker_count || 0)
  const totalCompleted = data?.analytics?.total_completed_sessions || 0

  return (
    <div style={{ padding: '24px 0', display: 'flex', flexDirection: 'column', gap: '28px' }}>
      
      {/* Header section */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.025em', margin: 0 }}>
            Transcoder Performance Dashboard
          </h1>
          <p style={{ fontSize: '0.88rem', color: '#94a3b8', marginTop: '4px', margin: 0 }}>
            Monitor hardware acceleration load, active worker pools, and routing failovers.
          </p>
        </div>
        <button 
          onClick={loadStatus} 
          style={{
            padding: '8px 16px',
            fontSize: '0.84rem',
            fontWeight: 600,
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '12px',
            color: '#cbd5e1',
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
        >
          Refresh Stats
        </button>
      </div>

      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '16px 20px', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: '16px', color: '#f87171', fontSize: '0.88rem' }}>
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Grid of system status cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
        
        {/* Card 1: Active Local Sessions */}
        <div style={{ padding: '20px 24px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '20px', display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ padding: '12px', background: 'rgba(168, 85, 247, 0.08)', border: '1px solid rgba(168, 85, 247, 0.15)', borderRadius: '16px', color: '#c084fc' }}>
            <Activity size={24} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Local Transcoders</div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc', marginTop: '2px' }}>{localCount} <span style={{ fontSize: '0.88rem', color: '#94a3b8', fontWeight: 500 }}>Active</span></div>
          </div>
        </div>

        {/* Card 2: Active Remote Sessions */}
        <div style={{ padding: '20px 24px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '20px', display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ padding: '12px', background: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.15)', borderRadius: '16px', color: '#38bdf8' }}>
            <Layers size={24} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Standalone Nodes</div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc', marginTop: '2px' }}>
              {data?.remote ? `${remoteCount} Active` : 'Offline'}
            </div>
          </div>
        </div>

        {/* Card 3: Total Completed */}
        <div style={{ padding: '20px 24px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '20px', display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ padding: '12px', background: 'rgba(52, 211, 153, 0.08)', border: '1px solid rgba(52, 211, 153, 0.15)', borderRadius: '16px', color: '#34d399' }}>
            <Database size={24} />
          </div>
          <div>
            <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sessions Managed</div>
            <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc', marginTop: '2px' }}>{totalCompleted} <span style={{ fontSize: '0.88rem', color: '#94a3b8', fontWeight: 500 }}>Completed</span></div>
          </div>
        </div>

      </div>

      {/* GPU & Hardware Utilization Row (Only if standalone GPU data exists, otherwise simulated CPU load) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px' }}>
        
        {/* Hardware Status Load */}
        <div style={{ padding: '24px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px' }}>
          <h3 style={{ fontSize: '0.96rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Sliders size={18} style={{ color: '#a855f7' }} />
            Transcoding System Load
          </h3>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '4px', marginBottom: '24px' }}>
            Current estimated computational resource allocation for decoding/encoding streams.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* CPU utilization bar */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '6px' }}>
                <span>CPU Decode Load</span>
                <strong>{activeSessions.filter(s => s.gpu_index == null).length * 8}%</strong>
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ 
                  height: '100%', 
                  width: `${Math.min(activeSessions.filter(s => s.gpu_index == null).length * 8, 100)}%`,
                  background: 'linear-gradient(90deg, #c084fc, #a855f7)',
                  borderRadius: '4px'
                }} />
              </div>
            </div>

            {/* GPU utilization bar */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#cbd5e1', marginBottom: '6px' }}>
                <span>GPU hardware acceleration (NVENC)</span>
                <strong>{activeSessions.filter(s => s.gpu_index != null).length * 12}%</strong>
              </div>
              <div style={{ height: '8px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ 
                  height: '100%', 
                  width: `${Math.min(activeSessions.filter(s => s.gpu_index != null).length * 12, 100)}%`,
                  background: 'linear-gradient(90deg, #38bdf8, #0284c7)',
                  borderRadius: '4px'
                }} />
              </div>
            </div>
          </div>
        </div>

        {/* Node Routing Policy Info */}
        <div style={{ padding: '24px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px' }}>
          <h3 style={{ fontSize: '0.96rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <Layers size={18} style={{ color: '#38bdf8' }} />
            Active Routing Strategy
          </h3>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '4px', marginBottom: '20px' }}>
            How transcoding jobs are dynamically allocated across the VMS cluster.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.82rem', color: '#cbd5e1' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '10px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ color: '#94a3b8' }}>Load Balancer Mode:</span>
              <strong style={{ color: '#34d399' }}>Active Failover</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '10px', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
              <span style={{ color: '#94a3b8' }}>Primary Engine:</span>
              <strong>Remote Standalone Transcoder</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#94a3b8' }}>Backup Engine:</span>
              <strong>Self-Transcoding (Local CPU)</strong>
            </div>
          </div>
        </div>

      </div>

      {/* Active Sessions List table */}
      <div style={{ padding: '28px', background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
          Active Transcoding Sessions ({activeSessions.length})
        </h3>
        
        {activeSessions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#64748b', fontSize: '0.88rem' }}>
            No streams are currently being transcoded. Sessions are spawned dynamically on-demand when user streams start.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem', color: '#cbd5e1', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  <th style={{ padding: '12px 16px' }}>Stream ID / Segment Key</th>
                  <th style={{ padding: '12px 16px' }}>Type</th>
                  <th style={{ padding: '12px 16px' }}>Hardware Mode</th>
                  <th style={{ padding: '12px 16px' }}>Uptime</th>
                  <th style={{ padding: '12px 16px' }}>Viewers</th>
                </tr>
              </thead>
              <tbody>
                {activeSessions.map((session, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', background: 'rgba(255,255,255,0.01)' }}>
                    <td style={{ padding: '16px', fontWeight: 700, color: '#f1f5f9', fontFamily: 'monospace' }}>
                      {session.stream_id}
                    </td>
                    <td style={{ padding: '16px' }}>
                      <span style={{ 
                        padding: '3px 9px', 
                        borderRadius: '8px', 
                        fontSize: '0.72rem', 
                        fontWeight: 600,
                        background: session.type === 'local' ? 'rgba(168,85,247,0.12)' : 'rgba(56,189,248,0.12)',
                        color: session.type === 'local' ? '#c084fc' : '#38bdf8',
                        border: `1px solid ${session.type === 'local' ? 'rgba(168,85,247,0.2)' : 'rgba(56,189,248,0.2)'}`
                      }}>
                        {session.type === 'local' ? 'Self-Transcode' : 'Remote Node'}
                      </span>
                    </td>
                    <td style={{ padding: '16px' }}>
                      <span style={{ color: session.gpu_index !== undefined && session.gpu_index !== null ? '#34d399' : '#cbd5e1' }}>
                        {session.gpu_index !== undefined && session.gpu_index !== null 
                          ? `NVENC GPU (${session.gpu_index})` 
                          : 'CPU (libx264)'
                        }
                      </span>
                    </td>
                    <td style={{ padding: '16px', color: '#94a3b8' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Clock size={14} />
                        {formatDuration(session.uptime_s)}
                      </div>
                    </td>
                    <td style={{ padding: '16px', fontWeight: 600, color: '#38bdf8' }}>
                      {session.viewers} viewers
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  )
}
