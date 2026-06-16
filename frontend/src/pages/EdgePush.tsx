import { useState, useEffect, useCallback } from 'react'
import { Wifi, WifiOff, AlertTriangle, CheckCircle2, RefreshCw, PlusCircle, Clock, HardDrive, Signal, X, Film, Play, ListFilter } from 'lucide-react'
import type { Camera } from '../types'
import { Player } from '../components/Player'
import { Playback } from './Playback'

// ─── Types ────────────────────────────────────────────────────────────────────

interface EdgeConnection {
  id: string
  camera_id: string
  connected_at: string | null
  disconnected_at: string | null
  last_frame_ts: string | null
  bytes_received: number
  status: 'CONNECTED' | 'DISCONNECTED' | 'TIMEOUT' | 'UNKNOWN'
  client_ip: string | null
}

interface UnregisteredCamera {
  camera_id: string
  is_active: boolean
  client_ip: string | null
  last_seen: string | null
  bytes_received: number
  first_seen: string | null
  status: string
}

interface EdgeStatus {
  active_edge_connections: number
  active_ffmpeg_relays: number
  online_streams: string[]
  offline_streams: string[]
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function fmtTime(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString()
}

function timeSince(iso: string | null) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

// ─── Register Modal ───────────────────────────────────────────────────────────

function RegisterModal({ cam, onClose, onRegistered }: {
  cam: UnregisteredCamera
  onClose: () => void
  onRegistered: () => void
}) {
  const [name, setName] = useState(cam.camera_id)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  async function doRegister() {
    setLoading(true)
    setError('')
    setMsg('')
    try {
      const res = await fetch(
        `/api/edge/register/${encodeURIComponent(cam.camera_id)}?name=${encodeURIComponent(name)}`,
        { method: 'POST' }
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Registration failed')
      setMsg(data.message || 'Registered successfully!')
      setTimeout(() => { onRegistered(); onClose() }, 1200)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
        border: '1px solid rgba(99,102,241,0.3)', borderRadius: '16px',
        padding: '28px', width: '420px', boxShadow: '0 24px 60px rgba(0,0,0,0.6)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color: '#e2e8f0', fontSize: '1rem', fontWeight: 700 }}>
            Register Edge Camera
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>
            Camera ID (from edge device)
          </label>
          <input
            value={cam.camera_id}
            disabled
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '8px', boxSizing: 'border-box',
              background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(148,163,184,0.15)',
              color: '#64748b', fontSize: '0.85rem', fontFamily: 'monospace'
            }}
          />
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>
            Display Name
          </label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Gate Camera 01"
            style={{
              width: '100%', padding: '8px 12px', borderRadius: '8px', boxSizing: 'border-box',
              background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(99,102,241,0.3)',
              color: '#e2e8f0', fontSize: '0.85rem', outline: 'none'
            }}
          />
        </div>

        <div style={{
          background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)',
          borderRadius: '8px', padding: '10px 12px', marginBottom: '20px',
          fontSize: '0.78rem', color: '#fbbf24', lineHeight: 1.5
        }}>
          ⚠ This will create a local DB entry so the server accepts future connections from <code style={{ fontFamily: 'monospace' }}>{cam.camera_id}</code>.
          The camera must also exist in UAT1 for full sync.
        </div>

        {msg && <div style={{ color: '#34d399', fontSize: '0.82rem', marginBottom: '12px' }}>{msg}</div>}
        {error && <div style={{ color: '#f87171', fontSize: '0.82rem', marginBottom: '12px' }}>{error}</div>}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: '8px', border: '1px solid rgba(148,163,184,0.2)',
            background: 'transparent', color: '#94a3b8', cursor: 'pointer', fontSize: '0.85rem'
          }}>
            Cancel
          </button>
          <button onClick={doRegister} disabled={loading || !name.trim()} style={{
            padding: '8px 20px', borderRadius: '8px', border: 'none',
            background: loading ? 'rgba(99,102,241,0.4)' : 'linear-gradient(135deg, #6366f1, #4f46e5)',
            color: '#fff', cursor: loading ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 600
          }}>
            {loading ? 'Registering…' : 'Register Camera'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function EdgePushPage({ edgeCameras }: { edgeCameras: Camera[] }) {
  const [activeSubTab, setActiveSubTab] = useState<'connections' | 'live' | 'playback'>('connections')
  const [connections, setConnections] = useState<EdgeConnection[]>([])
  const [unregistered, setUnregistered] = useState<UnregisteredCamera[]>([])
  const [status, setStatus] = useState<EdgeStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [registerModal, setRegisterModal] = useState<UnregisteredCamera | null>(null)
  const [tab, setTab] = useState<'connections' | 'unregistered'>('unregistered')
  const [lastRefresh, setLastRefresh] = useState<string>('—')

  // Live and Playback states
  const [selectedLiveCam, setSelectedLiveCam] = useState<Camera | undefined>()
  const [selectedPlaybackCam, setSelectedPlaybackCam] = useState<Camera | undefined>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [connRes, unregRes, statusRes] = await Promise.all([
        fetch('/api/edge/connections'),
        fetch('/api/edge/unregistered'),
        fetch('/api/edge/status'),
      ])
      if (connRes.ok) setConnections(await connRes.json())
      if (unregRes.ok) setUnregistered(await unregRes.json())
      if (statusRes.ok) setStatus(await statusRes.json())
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 10s
  useEffect(() => {
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [load])

  const activeConns = connections.filter(c => c.status === 'CONNECTED')

  return (
    <div style={{ padding: '24px', color: '#e2e8f0', minHeight: '100%' }}>

      {/* ── Sub-tab Navigation ── */}
      <div style={{
        display: 'flex',
        gap: '12px',
        marginBottom: '28px',
        padding: '6px',
        background: 'rgba(15, 23, 42, 0.4)',
        borderRadius: '16px',
        border: '1px solid rgba(148, 163, 184, 0.08)',
        width: 'fit-content'
      }}>
        {([
          { key: 'connections', label: 'Connections Monitor', icon: <Wifi size={16} /> },
          { key: 'live', label: 'Live Playback', icon: <Play size={16} /> },
          { key: 'playback', label: 'Recorded Playback', icon: <Film size={16} /> }
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => {
              setActiveSubTab(t.key)
              // Auto-select first camera if nothing selected
              if (t.key === 'live' && !selectedLiveCam && edgeCameras.length > 0) {
                setSelectedLiveCam(edgeCameras[0])
              }
              if (t.key === 'playback' && !selectedPlaybackCam && edgeCameras.length > 0) {
                setSelectedPlaybackCam(edgeCameras[0])
              }
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 20px',
              borderRadius: '12px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
              transition: 'all 0.2s ease',
              background: activeSubTab === t.key ? 'linear-gradient(135deg, #3b82f6, #8b5cf6)' : 'transparent',
              color: activeSubTab === t.key ? '#fff' : '#94a3b8',
              boxShadow: activeSubTab === t.key ? '0 8px 20px rgba(59, 130, 246, 0.25)' : 'none'
            }}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Connections Tab Content ── */}
      {activeSubTab === 'connections' && (
        <>
          {/* ── Header ── */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>
                Edge Push Monitor
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                Cameras pushing via TCP · Last refreshed {lastRefresh} · Auto-refreshes every 10s
              </p>
            </div>
            <button onClick={load} disabled={loading} style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '8px 16px', borderRadius: '8px', border: '1px solid rgba(99,102,241,0.3)',
              background: 'rgba(99,102,241,0.1)', color: '#a5b4fc', cursor: 'pointer', fontSize: '0.85rem'
            }}>
              <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
              Refresh
            </button>
          </div>

          {/* ── Stats ── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '24px' }}>
            {[
              { icon: <Signal size={18} color="#34d399" />, label: 'Active TCP Connections', value: status?.active_edge_connections ?? activeConns.length, color: '#34d399' },
              { icon: <Wifi size={18} color="#60a5fa" />, label: 'FFmpeg Relays', value: status?.active_ffmpeg_relays ?? 0, color: '#60a5fa' },
              { icon: <AlertTriangle size={18} color="#fbbf24" />, label: 'Unregistered Cameras', value: unregistered.length, color: unregistered.length > 0 ? '#fbbf24' : '#34d399' },
              { icon: <CheckCircle2 size={18} color="#a78bfa" />, label: 'Online Edge Streams', value: status?.online_streams?.length ?? 0, color: '#a78bfa' },
            ].map((s, i) => (
              <div key={i} style={{
                background: 'linear-gradient(135deg, rgba(30,41,59,0.9), rgba(15,23,42,0.9))',
                border: '1px solid rgba(148,163,184,0.1)', borderRadius: '12px', padding: '16px',
                display: 'flex', flexDirection: 'column', gap: '8px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {s.icon}
                  <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</span>
                </div>
                <div style={{ fontSize: '1.8rem', fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* ── Tabs ── */}
          <div style={{ display: 'flex', gap: '4px', marginBottom: '16px', borderBottom: '1px solid rgba(148,163,184,0.1)', paddingBottom: '0' }}>
            {([
              { key: 'unregistered', label: `⚠ Unregistered (${unregistered.length})` },
              { key: 'connections', label: `📡 All Connections (${connections.length})` },
            ] as const).map(t => (
              <button key={t.key} onClick={() => setTab(t.key)} style={{
                padding: '8px 18px', borderRadius: '8px 8px 0 0', border: 'none', cursor: 'pointer',
                fontSize: '0.82rem', fontWeight: tab === t.key ? 700 : 400,
                background: tab === t.key ? 'rgba(99,102,241,0.15)' : 'transparent',
                color: tab === t.key ? '#a5b4fc' : '#64748b',
                borderBottom: tab === t.key ? '2px solid #6366f1' : '2px solid transparent',
              }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* ── Unregistered Tab ── */}
          {tab === 'unregistered' && (
            <div>
              {unregistered.length === 0 ? (
                <div style={{
                  textAlign: 'center', padding: '60px 20px',
                  background: 'rgba(30,41,59,0.4)', borderRadius: '12px', border: '1px solid rgba(52,211,153,0.2)'
                }}>
                  <CheckCircle2 size={36} color="#34d399" style={{ marginBottom: '12px' }} />
                  <div style={{ color: '#34d399', fontWeight: 600 }}>All pushing cameras are registered!</div>
                  <div style={{ color: '#64748b', fontSize: '0.82rem', marginTop: '4px' }}>
                    No cameras pushing without a UAT1 registration found.
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{
                    background: 'rgba(234,179,8,0.07)', border: '1px solid rgba(234,179,8,0.2)',
                    borderRadius: '10px', padding: '12px 16px', marginBottom: '16px',
                    fontSize: '0.82rem', color: '#fbbf24', display: 'flex', alignItems: 'center', gap: '8px'
                  }}>
                    <AlertTriangle size={16} />
                    These cameras are actively pushing streams but are <strong>not registered in UAT1</strong>.
                    Register them locally so the server accepts their connections, then add them to UAT1 for full sync.
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {unregistered.map(cam => (
                      <div key={cam.camera_id} style={{
                        background: 'linear-gradient(135deg, rgba(30,41,59,0.95), rgba(15,23,42,0.95))',
                        border: `1px solid ${cam.is_active ? 'rgba(52,211,153,0.3)' : 'rgba(234,179,8,0.2)'}`,
                        borderRadius: '12px', padding: '16px 20px',
                        display: 'flex', alignItems: 'center', gap: '16px'
                      }}>
                        {/* Status indicator */}
                        <div style={{
                          width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0,
                          background: cam.is_active ? '#34d399' : '#f59e0b',
                          boxShadow: cam.is_active ? '0 0 8px rgba(52,211,153,0.6)' : 'none',
                          animation: cam.is_active ? 'pulse 2s infinite' : 'none'
                        }} />

                        {/* Info */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                            <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.95rem', color: '#e2e8f0' }}>
                              {cam.camera_id}
                            </span>
                            <span style={{
                              fontSize: '0.68rem', padding: '2px 8px', borderRadius: '99px', fontWeight: 700,
                              background: cam.is_active ? 'rgba(52,211,153,0.15)' : 'rgba(245,158,11,0.15)',
                              color: cam.is_active ? '#34d399' : '#f59e0b',
                              border: `1px solid ${cam.is_active ? 'rgba(52,211,153,0.3)' : 'rgba(245,158,11,0.3)'}`
                            }}>
                              {cam.status}
                            </span>
                            <span style={{
                              fontSize: '0.68rem', padding: '2px 8px', borderRadius: '99px',
                              background: 'rgba(234,179,8,0.1)', color: '#fbbf24',
                              border: '1px solid rgba(234,179,8,0.2)'
                            }}>
                              NOT IN UAT1
                            </span>
                          </div>
                          <div style={{ display: 'flex', gap: '20px', fontSize: '0.75rem', color: '#64748b' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <HardDrive size={11} /> {fmt(cam.bytes_received)}
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Clock size={11} /> First seen: {fmtTime(cam.first_seen)}
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              Last seen: {timeSince(cam.last_seen)}
                            </span>
                            {cam.client_ip && (
                              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                IP: {cam.client_ip}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Action */}
                        <button
                          onClick={() => setRegisterModal(cam)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: '6px',
                            padding: '8px 14px', borderRadius: '8px', border: '1px solid rgba(99,102,241,0.4)',
                            background: 'rgba(99,102,241,0.1)', color: '#a5b4fc',
                            cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap'
                          }}
                        >
                          <PlusCircle size={14} /> Register
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Connections Tab ── */}
          {tab === 'connections' && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.15)' }}>
                    {['Status', 'Camera ID', 'Client IP', 'Connected At', 'Last Frame', 'Bytes', 'Disconnected At'].map(h => (
                      <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: '#64748b', fontWeight: 600, fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {connections.map((conn, i) => (
                    <tr key={conn.id} style={{
                      borderBottom: '1px solid rgba(148,163,184,0.07)',
                      background: i % 2 === 0 ? 'rgba(30,41,59,0.3)' : 'transparent'
                    }}>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: '5px',
                          fontSize: '0.7rem', padding: '3px 10px', borderRadius: '99px', fontWeight: 700,
                          background: conn.status === 'CONNECTED' ? 'rgba(52,211,153,0.15)'
                            : conn.status === 'TIMEOUT' ? 'rgba(245,158,11,0.15)'
                            : 'rgba(148,163,184,0.1)',
                          color: conn.status === 'CONNECTED' ? '#34d399'
                            : conn.status === 'TIMEOUT' ? '#f59e0b'
                            : '#94a3b8',
                        }}>
                          {conn.status === 'CONNECTED' ? <Wifi size={10} /> : <WifiOff size={10} />}
                          {conn.status}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: '#e2e8f0', fontWeight: 600 }}>{conn.camera_id}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>{conn.client_ip || '—'}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>{fmtTime(conn.connected_at)}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>{timeSince(conn.last_frame_ts)}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>{fmt(conn.bytes_received)}</td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>{fmtTime(conn.disconnected_at)}</td>
                    </tr>
                  ))}
                  {connections.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
                        No edge connections recorded yet
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ── Live View Tab Content ── */}
      {activeSubTab === 'live' && (
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '24px', minHeight: '520px' }}>
          {/* Sidebar Camera List */}
          <div style={{
            background: 'rgba(15, 23, 42, 0.45)',
            border: '1px solid rgba(148, 163, 184, 0.1)',
            borderRadius: '16px',
            padding: '18px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px'
          }}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, margin: '0 0 6px 0', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <ListFilter size={14} /> Registered Edge
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', flex: 1 }}>
              {edgeCameras.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: '0.8rem', padding: '12px', textAlign: 'center' }}>
                  No registered edge cameras.
                </div>
              ) : (
                edgeCameras.map(cam => {
                  const isSelected = selectedLiveCam?.stream_id === cam.stream_id
                  return (
                    <button
                      key={cam.stream_id}
                      onClick={() => setSelectedLiveCam(cam)}
                      style={{
                        textAlign: 'left',
                        padding: '12px 14px',
                        borderRadius: '12px',
                        border: isSelected ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid rgba(148, 163, 184, 0.08)',
                        background: isSelected ? 'rgba(99, 102, 241, 0.12)' : 'rgba(30, 41, 59, 0.25)',
                        color: isSelected ? '#a5b4fc' : '#cbd5e1',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease'
                      }}
                    >
                      <div style={{ fontWeight: 700, fontSize: '0.86rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {cam.name}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '4px', fontFamily: 'monospace' }}>
                        {cam.stream_id}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Player Area */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            {selectedLiveCam ? (
              <div style={{ maxWidth: '800px', width: '100%', margin: '0 auto' }}>
                <Player
                  src={`/api/streams/${encodeURIComponent(selectedLiveCam.stream_id)}/live/index.m3u8`}
                  posterLabel={`${selectedLiveCam.name} — Live`}
                />
              </div>
            ) : (
              <div style={{
                textAlign: 'center',
                padding: '80px 20px',
                background: 'rgba(15, 23, 42, 0.3)',
                borderRadius: '20px',
                border: '1px solid rgba(148, 163, 184, 0.08)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%'
              }}>
                <Play size={40} style={{ color: '#64748b', marginBottom: '14px' }} />
                <div style={{ fontWeight: 600, color: '#e2e8f0', fontSize: '0.95rem' }}>Select an Edge Camera</div>
                <div style={{ color: '#64748b', fontSize: '0.8rem', marginTop: '6px' }}>
                  Choose an edge camera from the list on the left to display its live feed.
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Playback Tab Content ── */}
      {activeSubTab === 'playback' && (
        <div style={{ background: 'rgba(15, 23, 42, 0.3)', border: '1px solid rgba(148, 163, 184, 0.08)', borderRadius: '20px', padding: '20px' }}>
          {edgeCameras.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px' }}>
              <WifiOff size={48} style={{ color: '#64748b', margin: '0 auto 12px' }} />
              <h3 style={{ color: '#fff' }}>No registered edge cameras</h3>
              <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '4px' }}>Please register pushing cameras under the Connections tab first.</p>
            </div>
          ) : (
            <Playback
              cameras={edgeCameras}
              streamId={selectedPlaybackCam?.stream_id}
              cameraName={selectedPlaybackCam?.name}
              onSelectCamera={(cam) => setSelectedPlaybackCam(cam)}
            />
          )}
        </div>
      )}

      {/* ── Register Modal ── */}
      {registerModal && (
        <RegisterModal
          cam={registerModal}
          onClose={() => setRegisterModal(null)}
          onRegistered={load}
        />
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse {
          0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  )
}
