import React, { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Camera as CameraIcon, Save, X, Activity, Sliders, Database, AlertTriangle, Layers, Clock, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react'
import type { Camera } from '../types'
import { createCamera, updateCamera, deleteCamera, getSystemSettings, updateSystemSettings } from '../lib/api'
import { WebRTCPlayer } from '../components/WebRTCPlayer'

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
  const [activeTab, setActiveTab] = useState<'all' | 'upstream' | 'local'>('all')

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

  // RTSP input mode: 'combined' = full URL, 'custom' = individual fields
  const [rtspInputMode, setRtspInputMode] = useState<'combined' | 'custom'>('combined')
  const [rtspUsername, setRtspUsername] = useState('')
  const [rtspPassword, setRtspPassword] = useState('')
  const [rtspIpHost, setRtspIpHost] = useState('')
  const [rtspPort, setRtspPort] = useState('554')
  const [rtspPath, setRtspPath] = useState('')
  const [rtspQuery, setRtspQuery] = useState('')

  // Test connection states
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'failed'>('idle')
  const [testError, setTestError] = useState<string | null>(null)
  const [testStreamId, setTestStreamId] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)

  // Hardware configuration states
  const [cameraIp, setCameraIp] = useState('')
  const [cameraUser, setCameraUser] = useState('admin')
  const [cameraPassword, setCameraPassword] = useState('')

  // Target Hardware configuration states
  const [hwResolution, setHwResolution] = useState('')
  const [hwFps, setHwFps] = useState('')
  const [hwBitrate, setHwBitrate] = useState('')

  // Build RTSP URL from custom fields
  const buildRtspUrl = () => {
    if (!rtspIpHost) return ''
    let creds = ''
    if (rtspUsername && rtspPassword) creds = `${rtspUsername}:${encodeURIComponent(rtspPassword)}@`
    else if (rtspUsername) creds = `${rtspUsername}@`
    const portStr = rtspPort ? `:${rtspPort}` : ''
    let pathStr = rtspPath.trim()
    if (pathStr && !pathStr.startsWith('/')) pathStr = `/${pathStr}`
    let queryStr = rtspQuery.trim()
    if (queryStr && !queryStr.startsWith('?')) queryStr = `?${queryStr}`
    return `rtsp://${creds}${rtspIpHost.trim()}${portStr}${pathStr}${queryStr}`
  }

  // Parse RTSP URL into custom fields
  const parseRtspUrlIntoFields = (url: string) => {
    if (!url) return
    try {
      let cleanUrl = url
      if (cleanUrl.toLowerCase().startsWith('rtsp://')) cleanUrl = cleanUrl.substring(7)
      else if (cleanUrl.toLowerCase().startsWith('rtsps://')) cleanUrl = cleanUrl.substring(8)
      
      let username = '', password = '', rest = cleanUrl
      if (cleanUrl.includes('@')) {
        const atIdx = cleanUrl.lastIndexOf('@')
        const credsPart = cleanUrl.substring(0, atIdx)
        rest = cleanUrl.substring(atIdx + 1)
        if (credsPart.includes(':')) {
          const colonIdx = credsPart.indexOf(':')
          username = credsPart.substring(0, colonIdx)
          password = decodeURIComponent(credsPart.substring(colonIdx + 1))
        } else {
          username = credsPart
        }
      }
      
      let hostPort = rest.split('/')[0].split('?')[0]
      let pathAndQuery = rest.substring(hostPort.length)
      let host = hostPort, port = '554'
      if (hostPort.includes(':')) {
        const parts = hostPort.split(':')
        host = parts[0]
        port = parts[1]
      }
      
      let path = '', query = ''
      if (pathAndQuery.includes('?')) {
        const qIdx = pathAndQuery.indexOf('?')
        path = pathAndQuery.substring(0, qIdx)
        query = pathAndQuery.substring(qIdx + 1)
      } else {
        path = pathAndQuery
      }
      
      setRtspUsername(username)
      setRtspPassword(password)
      setRtspIpHost(host)
      setRtspPort(port)
      setRtspPath(path)
      setRtspQuery(query)
    } catch (e) {
      console.error('Failed to parse RTSP URL into fields:', e)
    }
  }

  // When switching to custom mode, parse the current combined URL
  const handleInputModeSwitch = (mode: 'combined' | 'custom') => {
    if (mode === 'custom' && rtspInputMode === 'combined') {
      parseRtspUrlIntoFields(streamUrl)
    } else if (mode === 'combined' && rtspInputMode === 'custom') {
      const built = buildRtspUrl()
      if (built) setStreamUrl(built)
    }
    setRtspInputMode(mode)
  }

  // Update combined URL when custom fields change
  useEffect(() => {
    if (rtspInputMode === 'custom') {
      const built = buildRtspUrl()
      if (built) setStreamUrl(built)
    }
  }, [rtspUsername, rtspPassword, rtspIpHost, rtspPort, rtspPath, rtspQuery, rtspInputMode])

  // Test connection handler
  const handleTestConnection = async () => {
    setTestStatus('testing')
    setTestError(null)
    setShowPreview(false)
    // Cleanup previous test stream
    if (testStreamId) {
      try { await fetch(`/api/cameras/test-connection/cleanup/${testStreamId}`, { method: 'POST' }) } catch {}
      setTestStreamId(null)
    }
    try {
      const body: any = { input_mode: rtspInputMode }
      if (rtspInputMode === 'combined') {
        body.rtsp_url = streamUrl
      } else {
        body.username = rtspUsername || undefined
        body.password = rtspPassword || undefined
        body.ip_host = rtspIpHost || undefined
        body.port = rtspPort ? parseInt(rtspPort, 10) : undefined
        body.path = rtspPath || undefined
        body.query = rtspQuery || undefined
      }
      const res = await fetch('/api/cameras/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      const data = await res.json()
      if (data.status === 'success') {
        setTestStatus('success')
        setTestStreamId(data.stream_id)
        setShowPreview(true)
        // If we get back the constructed URL and we're in custom mode, also update the combined URL
        if (data.rtsp_url && rtspInputMode === 'custom') {
          setStreamUrl(data.rtsp_url)
        }
      } else {
        setTestStatus('failed')
        setTestError(data.detail || 'Connection test failed')
      }
    } catch (err: any) {
      setTestStatus('failed')
      setTestError(err.message || 'Network error during test')
    }
  }

  // Cleanup test stream on unmount or form close
  const cleanupTestStream = () => {
    if (testStreamId) {
      fetch(`/api/cameras/test-connection/cleanup/${testStreamId}`, { method: 'POST' }).catch(() => {})
      setTestStreamId(null)
    }
    setTestStatus('idle')
    setTestError(null)
    setShowPreview(false)
  }

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
    setRtspInputMode('combined')
    setRtspUsername('')
    setRtspPassword('')
    setRtspIpHost('')
    setRtspPort('554')
    setRtspPath('')
    setRtspQuery('')
    cleanupTestStream()
  }

  const handleAddClick = () => {
    resetForm()
    setError(null)
    setSuccess(null)
    setShowAddForm(true)
    setEditingCamera(null)
  }

  const handleEditClick = (cam: Camera) => {
    const isUpstream = cam.camera_source === 'UPSTREAM' || (cam.camera_source !== 'LOCAL' && cam.synced_from_api)
    if (isUpstream) {
      setError('Cannot edit upstream managed cameras')
      return
    }
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
              onClick={() => { cleanupTestStream(); setShowAddForm(false); setEditingCamera(null) }}
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
            </div>

            {/* RTSP Connection Section */}
            <div style={{ padding: '20px', background: 'rgba(99, 102, 241, 0.04)', border: '1px solid rgba(99, 102, 241, 0.15)', borderRadius: '16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h4 style={{ margin: 0, color: '#818cf8', fontSize: '0.88rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={16} /> RTSP Stream Connection
                </h4>
                <div style={{ display: 'flex', gap: '4px', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '10px', padding: '3px' }}>
                  <button
                    type="button"
                    onClick={() => handleInputModeSwitch('combined')}
                    style={{
                      padding: '6px 14px', fontSize: '0.72rem', border: 'none', borderRadius: '8px', cursor: 'pointer', transition: 'all 0.2s',
                      background: rtspInputMode === 'combined' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                      color: rtspInputMode === 'combined' ? '#a5b4fc' : '#64748b',
                      fontWeight: rtspInputMode === 'combined' ? 600 : 400
                    }}
                  >Full URL</button>
                  <button
                    type="button"
                    onClick={() => handleInputModeSwitch('custom')}
                    style={{
                      padding: '6px 14px', fontSize: '0.72rem', border: 'none', borderRadius: '8px', cursor: 'pointer', transition: 'all 0.2s',
                      background: rtspInputMode === 'custom' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                      color: rtspInputMode === 'custom' ? '#a5b4fc' : '#64748b',
                      fontWeight: rtspInputMode === 'custom' ? 600 : 400
                    }}
                  >Custom Fields</button>
                </div>
              </div>

              {rtspInputMode === 'combined' ? (
                <div>
                  <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>RTSP Ingress URL *</label>
                  <input
                    value={streamUrl}
                    onChange={e => setStreamUrl(e.target.value)}
                    required
                    placeholder="rtsp://username:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0"
                    style={{ ...formInputStyle, fontFamily: 'monospace', fontSize: '0.82rem' }}
                  />
                  <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '6px' }}>Format: rtsp://[username:password@]host[:port][/path][?query]</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Username</label>
                      <input value={rtspUsername} onChange={e => setRtspUsername(e.target.value)} placeholder="admin" style={formInputStyle} />
                    </div>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Password</label>
                      <input type="password" value={rtspPassword} onChange={e => setRtspPassword(e.target.value)} placeholder="••••••••" style={formInputStyle} />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>IP Address / Hostname *</label>
                      <input value={rtspIpHost} onChange={e => setRtspIpHost(e.target.value)} required={rtspInputMode === 'custom'} placeholder="192.168.1.100" style={formInputStyle} />
                    </div>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Port</label>
                      <input type="number" value={rtspPort} onChange={e => setRtspPort(e.target.value)} placeholder="554" style={formInputStyle} />
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Path</label>
                      <input value={rtspPath} onChange={e => setRtspPath(e.target.value)} placeholder="/cam/realmonitor" style={{ ...formInputStyle, fontFamily: 'monospace', fontSize: '0.82rem' }} />
                    </div>
                    <div>
                      <label style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Query Parameters</label>
                      <input value={rtspQuery} onChange={e => setRtspQuery(e.target.value)} placeholder="channel=1&subtype=0" style={{ ...formInputStyle, fontFamily: 'monospace', fontSize: '0.82rem' }} />
                    </div>
                  </div>
                  {streamUrl && (
                    <div style={{ padding: '10px 14px', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '10px', fontFamily: 'monospace', fontSize: '0.75rem', color: '#94a3b8', wordBreak: 'break-all' }}>
                      <span style={{ color: '#64748b', marginRight: '8px' }}>Generated:</span>{streamUrl}
                    </div>
                  )}
                </div>
              )}

              {/* Test Connection Button + Status */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testStatus === 'testing' || !streamUrl}
                  className="batchBtn"
                  style={{
                    background: testStatus === 'success' ? 'rgba(16, 185, 129, 0.12)' : testStatus === 'failed' ? 'rgba(239, 68, 68, 0.12)' : 'rgba(99, 102, 241, 0.12)',
                    color: testStatus === 'success' ? '#34d399' : testStatus === 'failed' ? '#f87171' : '#a5b4fc',
                    borderColor: testStatus === 'success' ? 'rgba(16, 185, 129, 0.25)' : testStatus === 'failed' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(99, 102, 241, 0.25)',
                    fontSize: '0.78rem', padding: '8px 18px', transition: 'all 0.3s'
                  }}
                >
                  {testStatus === 'testing' ? (
                    <><RefreshCw size={14} style={{ marginRight: '6px', animation: 'spin 1s linear infinite' }} /> Testing Connection...</>
                  ) : testStatus === 'success' ? (
                    <><CheckCircle size={14} style={{ marginRight: '6px' }} /> Connected Successfully</>
                  ) : testStatus === 'failed' ? (
                    <><AlertCircle size={14} style={{ marginRight: '6px' }} /> Retry Test Connection</>
                  ) : (
                    <><Activity size={14} style={{ marginRight: '6px' }} /> Test Connection</>
                  )}
                </button>
                {testStatus === 'failed' && testError && (
                  <span style={{ fontSize: '0.72rem', color: '#f87171', maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={testError}>
                    {testError}
                  </span>
                )}
                {testStatus === 'success' && showPreview && (
                  <button
                    type="button"
                    onClick={() => setShowPreview(false)}
                    className="batchBtn"
                    style={{ background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8', fontSize: '0.72rem', padding: '6px 12px' }}
                  >
                    <X size={12} style={{ marginRight: '4px' }} /> Hide Preview
                  </button>
                )}
                {testStatus === 'success' && !showPreview && testStreamId && (
                  <button
                    type="button"
                    onClick={() => setShowPreview(true)}
                    className="batchBtn"
                    style={{ background: 'rgba(16, 185, 129, 0.08)', borderColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', fontSize: '0.72rem', padding: '6px 12px' }}
                  >
                    <CameraIcon size={12} style={{ marginRight: '4px' }} /> Show Preview
                  </button>
                )}
              </div>

              {/* Live Preview */}
              {showPreview && testStreamId && testStatus === 'success' && (
                <div style={{ borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(16, 185, 129, 0.2)', background: '#000', aspectRatio: '16/9', maxHeight: '360px', position: 'relative' }}>
                  <div style={{ position: 'absolute', top: '10px', left: '10px', zIndex: 10, display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(0,0,0,0.6)', borderRadius: '8px', padding: '4px 10px', fontSize: '0.7rem', color: '#34d399' }}>
                    <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#34d399', animation: 'pulse 2s infinite' }} />
                    LIVE PREVIEW
                  </div>
                  <WebRTCPlayer
                    streamId={testStreamId}
                    posterLabel="Test Preview"
                    onFallbackToHls={() => {}}
                    onClose={() => setShowPreview(false)}
                  />
                </div>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '0' }}>
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
                onClick={() => { cleanupTestStream(); setShowAddForm(false); setEditingCamera(null) }}
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '10px 0 0 0' }}>
            <h3 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#e2e8f0', margin: 0 }}>
              Registered Ingress Configurations ({cameras.length})
            </h3>
            
            {/* Source Tab Filters */}
            <div style={{ display: 'flex', gap: '6px', background: 'rgba(15, 23, 42, 0.4)', padding: '4px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <button
                onClick={() => setActiveTab('all')}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                  background: activeTab === 'all' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                  color: activeTab === 'all' ? '#60a5fa' : '#94a3b8',
                  transition: 'all 0.2s'
                }}
              >
                All ({cameras.length})
              </button>
              <button
                onClick={() => setActiveTab('upstream')}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                  background: activeTab === 'upstream' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                  color: activeTab === 'upstream' ? '#60a5fa' : '#94a3b8',
                  transition: 'all 0.2s'
                }}
              >
                Upstream ({cameras.filter(c => c.camera_source === 'UPSTREAM' || (c.camera_source !== 'LOCAL' && c.synced_from_api)).length})
              </button>
              <button
                onClick={() => setActiveTab('local')}
                style={{
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '0.76rem',
                  fontWeight: 600,
                  border: 'none',
                  cursor: 'pointer',
                  background: activeTab === 'local' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                  color: activeTab === 'local' ? '#60a5fa' : '#94a3b8',
                  transition: 'all 0.2s'
                }}
              >
                Local ({cameras.filter(c => c.camera_source === 'LOCAL' || (c.camera_source !== 'UPSTREAM' && !c.synced_from_api)).length})
              </button>
            </div>
          </div>

          {cameras.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', background: 'rgba(30, 41, 59, 0.2)', border: '1px dashed rgba(255,255,255,0.1)', borderRadius: '16px' }}>
              <CameraIcon size={32} style={{ color: '#64748b', marginBottom: '8px' }} />
              <div style={{ fontSize: '0.88rem', color: '#cbd5e1' }}>No camera configurations found.</div>
              <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: '4px' }}>Click "Register Local Camera" above to configure your first camera feed.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {cameras
                .filter((cam) => {
                  const isUpstream = cam.camera_source === 'UPSTREAM' || (cam.camera_source !== 'LOCAL' && cam.synced_from_api)
                  if (activeTab === 'upstream') return isUpstream
                  if (activeTab === 'local') return !isUpstream
                  return true
                })
                .map((cam) => {
                  const stream = cam.streams[0]
                  const isUpstream = cam.camera_source === 'UPSTREAM' || (cam.camera_source !== 'LOCAL' && cam.synced_from_api)
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
                            {isUpstream ? (
                              <span style={{ padding: '2px 8px', borderRadius: '8px', fontSize: '0.68rem', fontWeight: 600, background: 'rgba(59,130,246,0.12)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.2)' }} title="Configuration controlled externally">
                                Managed by Upstream
                              </span>
                            ) : (
                              <span style={{ padding: '2px 8px', borderRadius: '8px', fontSize: '0.68rem', fontWeight: 600, background: 'rgba(52,211,153,0.12)', color: '#34d399', border: '1px solid rgba(52,211,153,0.2)' }}>
                                Managed Locally
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
                        {!isUpstream ? (
                          <>
                            <button 
                              onClick={() => handleEditClick(cam)}
                              className="batchBtn"
                              title="Edit Camera Details"
                              style={{ padding: '8px', minWidth: 'auto', background: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.08)', color: '#94a3b8' }}
                            >
                              <Edit size={16} />
                            </button>
                            <button 
                              onClick={() => stream && handleDelete(stream.stream_id)}
                              className="batchBtn"
                              title="Delete Camera Configuration"
                              style={{ padding: '8px', minWidth: 'auto', background: 'rgba(239,68,68,0.05)', borderColor: 'rgba(239,68,68,0.1)', color: '#f87171' }}
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={onRefresh}
                            className="batchBtn"
                            title="Refresh Upstream Configuration"
                            style={{ padding: '8px', minWidth: 'auto', background: 'rgba(59,130,246,0.05)', borderColor: 'rgba(59,130,246,0.1)', color: '#60a5fa' }}
                          >
                            <RefreshCw size={16} style={{ animation: loading ? 'spin 1.5s linear infinite' : 'none' }} />
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
