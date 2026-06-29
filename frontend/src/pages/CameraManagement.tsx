import React, { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Camera as CameraIcon, Save, X, Activity, Sliders, Database, AlertTriangle, Layers, Clock } from 'lucide-react'
import type { Camera } from '../types'
import { createCamera, updateCamera, deleteCamera, getSystemSettings, updateSystemSettings } from '../lib/api'

type Props = {
  cameras: Camera[]
  onRefresh: () => void
}

export function CameraManagement({ cameras, onRefresh }: Props) {
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [useUpstreamCameras, setUseUpstreamCameras] = useState(true)
  const [enableDeviceConfig, setEnableDeviceConfig] = useState(false)
  const [enableLocalTranscode, setEnableLocalTranscode] = useState(false)
  const [settingLoading, setSettingLoading] = useState(false)

  useEffect(() => {
    async function loadSettings() {
      try {
        const data = await getSystemSettings()
        setUseUpstreamCameras(data.use_upstream_cameras)
        setEnableDeviceConfig(!!data.enable_device_config)
        setEnableLocalTranscode(!!data.enable_local_transcode)
      } catch (err) {
        console.error('Failed to load system settings:', err)
      }
    }
    loadSettings()
  }, [])

  const handleToggleUpstream = async (val: boolean) => {
    setSettingLoading(true)
    setError(null)
    setSuccess(null)
    try {
      await updateSystemSettings(val)
      setUseUpstreamCameras(val)
      setSuccess(val ? 'Upstream Sync enabled successfully!' : 'Local-Only Mode enabled! Synced cameras are hidden.')
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Failed to update system settings')
    } finally {
      setSettingLoading(false)
    }
  }

  // Form states
  const [name, setName] = useState('')
  const [sourceCameraId, setSourceCameraId] = useState<number>(1)
  const [make, setMake] = useState('')
  const [streamId, setStreamId] = useState('')
  const [profileType, setProfileType] = useState('MAIN')
  const [resolution, setResolution] = useState('1920x1080')
  const [fps, setFps] = useState<number>(30)
  const [codec, setCodec] = useState('H264')
  const [bitrate, setBitrate] = useState<string>('')
  const [streamUrl, setStreamUrl] = useState('')
  const [alwaysOn, setAlwaysOn] = useState(false)
  const [transcode, setTranscode] = useState(false)
  const [active, setActive] = useState(true)

  // Hardware configuration states
  const [cameraIp, setCameraIp] = useState('')
  const [cameraUser, setCameraUser] = useState('admin')
  const [cameraPassword, setCameraPassword] = useState('')

  // Target Hardware configuration states
  const [hwResolution, setHwResolution] = useState('')
  const [hwFps, setHwFps] = useState('')
  const [hwBitrate, setHwBitrate] = useState('')

  // Extractor utility for RTSP credentials
  const extractCredentialsFromRtsp = (rtspUrl: string) => {
    if (!rtspUrl) return { ip: '', username: 'admin', password: '' }
    try {
      let cleanUrl = rtspUrl
      if (cleanUrl.toLowerCase().startsWith('rtsp://')) {
        cleanUrl = cleanUrl.substring(7)
      }
      let username = 'admin'
      let password = ''
      let ip = ''
      
      if (cleanUrl.includes('@')) {
        const parts = cleanUrl.split('@')
        const creds = parts[0]
        const hostPart = parts[1]
        
        if (creds.includes(':')) {
          const credParts = creds.split(':')
          username = credParts[0]
          password = decodeURIComponent(credParts[1])
        } else {
          username = creds
        }
        
        const hostOnly = hostPart.split('/')[0]
        ip = hostOnly.split(':')[0]
      } else {
        const hostOnly = cleanUrl.split('/')[0]
        ip = hostOnly.split(':')[0]
      }
      
      return { ip, username, password }
    } catch (e) {
      console.error('Failed to parse RTSP URL:', e)
      return { ip: '', username: 'admin', password: '' }
    }
  }

  // Reset form helper
  const resetForm = () => {
    setName('')
    setSourceCameraId(cameras.length > 0 ? Math.max(...cameras.map(c => c.source_camera_id)) + 1 : 1)
    setMake('')
    setStreamId('')
    setProfileType('MAIN')
    setResolution('1920x1080')
    setFps(30)
    setCodec('H264')
    setBitrate('')
    setStreamUrl('')
    setAlwaysOn(false)
    setTranscode(false)
    setActive(true)
    setCameraIp('')
    setCameraUser('admin')
    setCameraPassword('')
    setHwResolution('')
    setHwFps('')
    setHwBitrate('')
  }

  const handleAddClick = () => {
    resetForm()
    setError(null)
    setSuccess(null)
    setShowAddForm(true)
    setEditingCamera(null)
  }

  const handleEditClick = (cam: Camera) => {
    setError(null)
    setSuccess(null)
    setEditingCamera(cam)
    setShowAddForm(false)
    
    // Fill form
    setName(cam.name)
    setSourceCameraId(cam.source_camera_id)
    setMake(cam.make || '')
    setActive(cam.active)
    
    const stream = cam.streams[0]
    if (stream) {
      setStreamId(stream.stream_id)
      setProfileType(stream.profile_type)
      setResolution(stream.resolution)
      setFps(stream.fps)
      setCodec(stream.codec)
      setBitrate(stream.bitrate ? stream.bitrate.toString() : '')
      setStreamUrl(stream.stream_url)
      setAlwaysOn(!!stream.always_on)
      setTranscode(!!stream.transcode)

      // Prefill hardware configuration fields using database values & parsed RTSP creds
      setHwResolution(stream.resolution)
      setHwFps(stream.fps ? stream.fps.toString() : '')
      setHwBitrate(stream.bitrate ? stream.bitrate.toString() : '')

      const extracted = extractCredentialsFromRtsp(stream.stream_url)
      if (extracted.ip) {
        setCameraIp(`https://${extracted.ip}`)
      } else {
        setCameraIp('')
      }
      setCameraUser(extracted.username || 'admin')
      setCameraPassword(extracted.password || '')
    } else {
      setCameraIp('')
      setCameraUser('admin')
      setCameraPassword('')
      setHwResolution('')
      setHwFps('')
      setHwBitrate('')
      setTranscode(false)
    }
  }

  const handleDelete = async (streamIdToDelete: string) => {
    if (!confirm('Are you sure you want to delete this camera and all its recording directories? This action cannot be undone.')) {
      return
    }

    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      await deleteCamera(streamIdToDelete)
      setSuccess('Camera deleted successfully!')
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Failed to delete camera')
    } finally {
      setLoading(false)
    }
  }

  const handleApplyHardwareConfig = async () => {
    setLoading(true)
    setError(null)
    setSuccess(null)

    let width: number | null = null
    let height: number | null = null
    if (hwResolution && hwResolution.includes('x')) {
      const parts = hwResolution.split('x')
      width = Number(parts[0])
      height = Number(parts[1])
    }

    try {
      const streamToConfigure = editingCamera?.streams[0]?.stream_id || streamId
      if (!streamToConfigure) {
        throw new Error('No stream selected to configure')
      }

      const res = await fetch('/api/cameras/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stream_id: streamToConfigure,
          fps: hwFps ? Number(hwFps) : null,
          bitrate: hwBitrate ? Number(hwBitrate) : null,
          width: width,
          height: height,
          ip: cameraIp || null,
          username: cameraUser || null,
          password: cameraPassword || null
        })
      })

      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || 'Failed to apply configuration to camera hardware')
      }

      setSuccess('Successfully applied parameters to the physical camera and updated VMS database!')
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Error applying hardware configuration')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setSuccess(null)

    const payload = {
      name,
      active,
      make: make || null,
      resolution,
      fps: Number(fps),
      codec,
      bitrate: bitrate ? Number(bitrate) : null,
      stream_url: streamUrl,
      always_on: alwaysOn,
      transcode: transcode
    }

    try {
      if (editingCamera) {
        const streamToEdit = editingCamera.streams[0]?.stream_id || streamId
        await updateCamera(streamToEdit, payload)
        setSuccess('Camera updated successfully!')
        setEditingCamera(null)
      } else {
        const createPayload = {
          ...payload,
          source_camera_id: Number(sourceCameraId),
          stream_id: streamId || `cam_${sourceCameraId}_main`,
          profile_type: profileType,
          stream_mode: 'AUTO'
        }
        await createCamera(createPayload)
        setSuccess('Camera registered successfully!')
        setShowAddForm(false)
      }
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Failed to save camera configuration')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="cameraManagementPage" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
            Camera Inventory & Configuration
          </h2>
          <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
            Manage local on-premise cameras and upstream sync settings.
          </span>
        </div>
        <button 
          onClick={handleAddClick}
          className="batchBtn start"
          style={{ background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)', border: 'none', gap: '6px' }}
        >
          <Plus size={16} /> Register Local Camera
        </button>
      </div>

      {/* Upstream Sync Mode Toggle */}
      {!showAddForm && !editingCamera && (
        <div style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(30, 41, 59, 0.4)', borderRadius: '16px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#f8fafc' }}>
              Cloud Upstream Synchronization
            </span>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
              {useUpstreamCameras 
                ? "Active: Synced cameras from UAT1 cloud are visible alongside local cameras."
                : "Active: Local-Only mode. Cloud API sync is disabled, and only manual configurations are visible."}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {settingLoading && <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Updating...</span>}
            <label className="switch">
              <input 
                type="checkbox" 
                checked={useUpstreamCameras} 
                onChange={(e) => handleToggleUpstream(e.target.checked)}
                disabled={settingLoading}
              />
              <span className="slider"></span>
            </label>
          </div>
        </div>
      )}

      {/* Status Notifications */}
      {error && (
        <div style={{ padding: '12px 16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '12px', fontSize: '0.85rem', color: '#f87171' }}>
          {error}
        </div>
      )}
      {success && (
        <div style={{ padding: '12px 16px', background: 'rgba(52, 211, 153, 0.1)', border: '1px solid rgba(52, 211, 153, 0.2)', borderRadius: '12px', fontSize: '0.85rem', color: '#34d399' }}>
          {success}
        </div>
      )}

      {/* Form (Add or Edit) */}
      {(showAddForm || editingCamera) && (
        <div style={{ padding: '24px', background: 'rgba(30, 41, 59, 0.3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h3 style={{ margin: 0, color: '#f8fafc', fontSize: '1rem', fontWeight: 700 }}>
              {editingCamera ? `Edit Camera: ${editingCamera.name}` : 'Register Local Camera'}
            </h3>
            <button 
              onClick={() => { setShowAddForm(false); setEditingCamera(null) }}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              <X size={20} />
            </button>
          </div>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Display Name *</label>
                <input value={name} onChange={e => setName(e.target.value)} required placeholder="e.g. Main Lobby" style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Source Camera ID (Unique Integer) *</label>
                <input type="number" value={sourceCameraId} onChange={e => setSourceCameraId(Number(e.target.value))} required disabled={!!editingCamera} style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Camera Make/Model</label>
                <input value={make} onChange={e => setMake(e.target.value)} placeholder="e.g. Hikvision" style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Stream ID (e.g. LOBBY_MAIN) *</label>
                <input value={streamId} onChange={e => setStreamId(e.target.value)} required disabled={!!editingCamera} placeholder="e.g. LOBBY_MAIN" style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Stream Profile</label>
                <select value={profileType} onChange={e => setProfileType(e.target.value)} disabled={!!editingCamera} style={formInputStyle}>
                  <option value="MAIN">MAIN (High Quality / Recording)</option>
                  <option value="SUB">SUB (Low Quality / Grid view)</option>
                  <option value="MOBILE">MOBILE</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Resolution</label>
                <input value={resolution} onChange={e => setResolution(e.target.value)} placeholder="e.g. 1920x1080" style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>FPS</label>
                <input type="number" value={fps} onChange={e => setFps(Number(e.target.value))} style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Video Codec</label>
                <select value={codec} onChange={e => setCodec(e.target.value)} style={formInputStyle}>
                  <option value="H264">H264</option>
                  <option value="H265">H265 (Auto-transcoded for web if needed)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Bitrate (kbps)</label>
                <input type="number" value={bitrate} onChange={e => setBitrate(e.target.value)} placeholder="e.g. 2048" style={formInputStyle} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>RTSP Ingress URL *</label>
                <input value={streamUrl} onChange={e => setStreamUrl(e.target.value)} required placeholder="rtsp://host:port/stream" style={formInputStyle} />
              </div>
            </div>

            <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: '#cbd5e1' }}>
                <input type="checkbox" checked={alwaysOn} onChange={e => setAlwaysOn(e.target.checked)} />
                Enable 24/7 Disk Recording (Always On)
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: '#cbd5e1' }}>
                <input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} />
                Camera Enabled (Active Ingress)
              </label>
              {enableLocalTranscode && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.82rem', color: '#cbd5e1' }}>
                  <input type="checkbox" checked={transcode} onChange={e => setTranscode(e.target.checked)} />
                  Enable Local Transcoding (Server-Side Enforcement)
                </label>
              )}
            </div>

            {editingCamera && enableDeviceConfig && (
              <div style={{ padding: '20px', background: 'rgba(59, 130, 246, 0.04)', border: '1px solid rgba(59, 130, 246, 0.16)', borderRadius: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <h4 style={{ margin: 0, color: '#60a5fa', fontSize: '0.88rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Sliders size={16} /> Remote Device ONVIF Configuration
                </h4>
                <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.76rem' }}>
                  Apply parameter changes directly to the physical camera hardware. Leaving a field empty will keep its current value on the camera.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px' }}>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Camera IP / HTTPS Base URL</label>
                    <input value={cameraIp} onChange={e => setCameraIp(e.target.value)} placeholder="e.g. https://172.20.100.245" style={formInputStyle} />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>ONVIF Username</label>
                    <input value={cameraUser} onChange={e => setCameraUser(e.target.value)} placeholder="admin" style={formInputStyle} />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>ONVIF Password</label>
                    <input type="password" value={cameraPassword} onChange={e => setCameraPassword(e.target.value)} placeholder="password" style={formInputStyle} />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '14px' }}>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Hardware Resolution (Optional)</label>
                    <input value={hwResolution} onChange={e => setHwResolution(e.target.value)} placeholder="e.g. 1920x1080 (leave blank to skip)" style={formInputStyle} />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Hardware FPS (Optional)</label>
                    <input type="number" value={hwFps} onChange={e => setHwFps(e.target.value)} placeholder="e.g. 25 (leave blank to skip)" style={formInputStyle} />
                  </div>
                  <div>
                    <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Hardware Bitrate kbps (Optional)</label>
                    <input type="number" value={hwBitrate} onChange={e => setHwBitrate(e.target.value)} placeholder="e.g. 2048 (leave blank to skip)" style={formInputStyle} />
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <button 
                    type="button" 
                    onClick={handleApplyHardwareConfig}
                    disabled={loading}
                    className="batchBtn"
                    style={{
                      background: 'rgba(59, 130, 246, 0.12)',
                      color: '#60a5fa',
                      borderColor: 'rgba(59, 130, 246, 0.25)',
                      fontSize: '0.78rem',
                      padding: '8px 14px'
                    }}
                  >
                    {loading ? 'Applying to Camera...' : 'Apply & Save Config to Physical Camera'}
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '10px' }}>
              <button 
                type="button" 
                onClick={() => { setShowAddForm(false); setEditingCamera(null) }}
                className="batchBtn"
                style={{ background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', color: '#cbd5e1' }}
              >
                Cancel
              </button>
              <button 
                type="submit" 
                disabled={loading}
                className="batchBtn start"
                style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)', border: 'none', minWidth: '100px' }}
              >
                {loading ? 'Saving...' : <><Save size={14} style={{ marginRight: '6px' }} /> Save Camera</>}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Camera Inventory List */}
      {!showAddForm && !editingCamera && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <h3 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#e2e8f0', margin: '10px 0 0 0' }}>
            Registered Ingress Configurations ({cameras.length})
          </h3>

          {cameras.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', background: 'rgba(30, 41, 59, 0.2)', border: '1px dashed rgba(255,255,255,0.1)', borderRadius: '16px' }}>
              <CameraIcon size={32} style={{ color: '#64748b', marginBottom: '8px' }} />
              <div style={{ fontSize: '0.88rem', color: '#cbd5e1' }}>No camera configurations found.</div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '4px' }}>Click "Register Local Camera" above to configure your first camera feed.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {cameras.map((cam) => {
                const stream = cam.streams[0]
                return (
                  <div 
                    key={cam.id} 
                    style={{ 
                      padding: '16px 20px', 
                      background: 'rgba(15, 23, 42, 0.3)', 
                      border: '1px solid rgba(255,255,255,0.05)', 
                      borderRadius: '16px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <div style={{ padding: '10px', background: 'rgba(59, 130, 246, 0.08)', borderRadius: '12px', border: '1px solid rgba(59, 130, 246, 0.15)', color: '#60a5fa' }}>
                        <CameraIcon size={20} />
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#f8fafc' }}>{cam.name}</span>
                          <span style={{ padding: '2px 8px', borderRadius: '8px', fontSize: '0.68rem', fontWeight: 600, background: cam.active ? 'rgba(52,211,153,0.12)' : 'rgba(239,68,68,0.12)', color: cam.active ? '#34d399' : '#f87171', border: cam.active ? '1px solid rgba(52,211,153,0.2)' : '1px solid rgba(239,68,68,0.2)' }}>
                            {cam.active ? 'Active' : 'Disabled'}
                          </span>
                          {cam.synced_from_api && (
                            <span style={{ padding: '2px 8px', borderRadius: '8px', fontSize: '0.68rem', fontWeight: 600, background: 'rgba(59,130,246,0.12)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.2)' }}>
                              Synced (Cloud)
                            </span>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '0.76rem', color: '#94a3b8' }}>
                          <span>Make: {cam.make || 'Generic'}</span>
                          <span>•</span>
                          <span>Stream ID: <code style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{stream?.stream_id || '—'}</code></span>
                          <span>•</span>
                          <span>RTSP Ingress: <code style={{ fontFamily: 'monospace' }}>{stream?.stream_url || '—'}</code></span>
                          {stream?.always_on && (
                            <>
                              <span>•</span>
                              <span style={{ color: '#fbbf24', fontWeight: 500 }}>24/7 Rec</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button 
                        onClick={() => handleEditClick(cam)}
                        className="batchBtn"
                        title="Edit Camera Details"
                        style={{ padding: '8px', minWidth: 'auto', background: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' }}
                      >
                        <Edit size={16} />
                      </button>
                      {!cam.synced_from_api && (
                        <button 
                          onClick={() => stream && handleDelete(stream.stream_id)}
                          className="batchBtn"
                          title="Delete Camera Configuration"
                          style={{ padding: '8px', minWidth: 'auto', background: 'rgba(239,68,68,0.05)', borderColor: 'rgba(239,68,68,0.1)', color: '#f87171' }}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const formInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  borderRadius: '10px',
  boxSizing: 'border-box',
  background: 'rgba(15, 23, 42, 0.6)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#e2e8f0',
  fontSize: '0.85rem',
  outline: 'none',
  marginTop: '4px'
}
