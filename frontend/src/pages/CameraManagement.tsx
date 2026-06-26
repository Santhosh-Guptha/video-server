import React, { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Camera as CameraIcon, Save, X, Activity, Sliders, Database, AlertTriangle, Layers, Clock, Copy, Loader2 } from 'lucide-react'
import type { Camera } from '../types'
import { createCamera, updateCamera, deleteCamera, getSystemSettings, updateSystemSettings, testRtspConnection } from '../lib/api'

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
  const [settingLoading, setSettingLoading] = useState(false)

  useEffect(() => {
    async function loadSettings() {
      try {
        const data = await getSystemSettings()
        setUseUpstreamCameras(data.use_upstream_cameras)
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

  // Ingress RTSP connection testing state
  const [testingConnection, setTestingConnection] = useState(false)
  const [connectionTestResult, setConnectionTestResult] = useState<{ success: boolean; message: string } | null>(null)

  // Batch selection state
  const [selectedIds, setSelectedIds] = useState<string[]>([])

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
  const [active, setActive] = useState(true)

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
    setActive(true)
    setConnectionTestResult(null)
  }

  const handleTestConnection = async () => {
    if (!streamUrl) {
      setError('Please enter an RTSP URL to test')
      return
    }
    setTestingConnection(true)
    setConnectionTestResult(null)
    try {
      const res = await testRtspConnection(streamUrl)
      setConnectionTestResult(res)
    } catch (err: any) {
      setConnectionTestResult({ success: false, message: err.message || 'Connection test failed' })
    } finally {
      setTestingConnection(false)
    }
  }

  const handleCloneClick = (cam: Camera) => {
    resetForm()
    setError(null)
    setSuccess(null)
    setEditingCamera(null)
    setShowAddForm(true)

    // Pre-fill fields
    setName(`${cam.name} (Clone)`)
    
    // Find next unique source_camera_id
    const nextId = cameras.length > 0 ? Math.max(...cameras.map(c => c.source_camera_id)) + 1 : 1
    setSourceCameraId(nextId)
    setMake(cam.make || '')
    setActive(cam.active)
    
    const stream = cam.streams[0]
    if (stream) {
      setStreamId(`${stream.stream_id}_clone`)
      setProfileType(stream.profile_type)
      setResolution(stream.resolution)
      setFps(stream.fps)
      setCodec(stream.codec)
      setBitrate(stream.bitrate ? stream.bitrate.toString() : '')
      setStreamUrl(stream.stream_url)
      setAlwaysOn(!!stream.always_on)
    }
  }

  const handleToggleSelectAll = () => {
    if (selectedIds.length === cameras.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(cameras.map(c => c.streams[0]?.stream_id).filter(Boolean) as string[])
    }
  }

  const handleToggleSelect = (sId: string) => {
    setSelectedIds(prev => prev.includes(sId) ? prev.filter(id => id !== sId) : [...prev, sId])
  }

  const handleBatchActive = async (activeState: boolean) => {
    if (selectedIds.length === 0) return
    setLoading(true)
    setError(null)
    setSuccess(null)
    let count = 0
    try {
      for (const sId of selectedIds) {
        const cam = cameras.find(c => c.streams.some(s => s.stream_id === sId))
        if (!cam) continue
        const mainStream = cam.streams[0]
        if (!mainStream) continue
        await updateCamera(sId, {
          name: cam.name,
          active: activeState,
          make: cam.make,
          resolution: mainStream.resolution,
          fps: mainStream.fps,
          codec: mainStream.codec,
          bitrate: mainStream.bitrate,
          stream_url: mainStream.stream_url,
          always_on: mainStream.always_on
        })
        count++
      }
      setSuccess(`Successfully updated active state for ${count} cameras!`)
      setSelectedIds([])
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Batch update active state failed')
    } finally {
      setLoading(false)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) return
    if (!confirm(`Are you sure you want to delete ${selectedIds.length} cameras? This will permanently delete their configuration and recordings directories, and cannot be undone.`)) {
      return
    }
    setLoading(true)
    setError(null)
    setSuccess(null)
    let count = 0
    try {
      for (const sId of selectedIds) {
        const cam = cameras.find(c => c.streams.some(s => s.stream_id === sId))
        if (cam && !cam.synced_from_api) {
          await deleteCamera(sId)
          count++
        }
      }
      setSuccess(`Successfully deleted ${count} local cameras!`)
      setSelectedIds([])
      onRefresh()
    } catch (err: any) {
      setError(err.message || 'Batch delete failed')
    } finally {
      setLoading(false)
    }
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
      always_on: alwaysOn
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
                <input value={name} onChange={e => setName(e.target.value)} required placeholder="e.g. Main Lobby" className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Source Camera ID (Unique Integer) *</label>
                <input type="number" value={sourceCameraId} onChange={e => setSourceCameraId(Number(e.target.value))} required disabled={!!editingCamera} className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Camera Make/Model</label>
                <input value={make} onChange={e => setMake(e.target.value)} placeholder="e.g. Hikvision" className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Stream ID (e.g. LOBBY_MAIN) *</label>
                <input value={streamId} onChange={e => setStreamId(e.target.value)} required disabled={!!editingCamera} placeholder="e.g. LOBBY_MAIN" className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Stream Profile</label>
                <select value={profileType} onChange={e => setProfileType(e.target.value)} disabled={!!editingCamera} className="vms-select">
                  <option value="MAIN">MAIN (High Quality / Recording)</option>
                  <option value="SUB">SUB (Low Quality / Grid view)</option>
                  <option value="MOBILE">MOBILE</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Resolution</label>
                <input value={resolution} onChange={e => setResolution(e.target.value)} placeholder="e.g. 1920x1080" className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>FPS</label>
                <input type="number" value={fps} onChange={e => setFps(Number(e.target.value))} className="vms-input" />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Video Codec</label>
                <select value={codec} onChange={e => setCodec(e.target.value)} className="vms-select">
                  <option value="H264">H264</option>
                  <option value="H265">H265 (Auto-transcoded for web if needed)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>Bitrate (kbps)</label>
                <input type="number" value={bitrate} onChange={e => setBitrate(e.target.value)} placeholder="e.g. 2048" className="vms-input" />
              </div>
              <div style={{ gridColumn: 'span 2' }}>
                <label style={{ fontSize: '0.75rem', color: '#94a3b8', display: 'block', marginBottom: '6px' }}>RTSP Ingress URL *</label>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <input
                    value={streamUrl}
                    onChange={e => setStreamUrl(e.target.value)}
                    required
                    placeholder="rtsp://host:port/stream"
                    className="vms-input"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    onClick={handleTestConnection}
                    disabled={testingConnection || !streamUrl}
                    className="batchBtn"
                    style={{
                      padding: '8px 16px',
                      background: 'rgba(59, 130, 246, 0.1)',
                      color: '#60a5fa',
                      borderColor: 'rgba(59, 130, 246, 0.2)',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      whiteSpace: 'nowrap'
                    }}
                  >
                    {testingConnection ? (
                      <>
                        <Loader2 className="spin" size={14} style={{ animation: 'spin 1s linear infinite' }} />
                        Testing...
                      </>
                    ) : 'Test Connection'}
                  </button>
                </div>
                {connectionTestResult && (
                  <div style={{
                    marginTop: '8px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    fontSize: '0.78rem',
                    background: connectionTestResult.success ? 'rgba(52, 211, 153, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                    border: `1px solid ${connectionTestResult.success ? 'rgba(52, 211, 153, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
                    color: connectionTestResult.success ? '#34d399' : '#f87171'
                  }}>
                    {connectionTestResult.message}
                  </div>
                )}
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
            </div>

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
          
          {/* Header & Select All */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '10px 0 0 0' }}>
            <h3 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#e2e8f0', margin: 0 }}>
              Registered Ingress Configurations ({cameras.length})
            </h3>
            {cameras.length > 0 && (
              <button
                type="button"
                onClick={handleToggleSelectAll}
                className="batchBtn"
                style={{ fontSize: '0.78rem', padding: '6px 12px' }}
              >
                {selectedIds.length === cameras.length ? 'Deselect All' : 'Select All'}
              </button>
            )}
          </div>

          {/* Batch Actions Toolbar */}
          {selectedIds.length > 0 && (
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '12px 18px', background: 'rgba(168, 85, 247, 0.12)', border: '1px solid rgba(168, 85, 247, 0.25)',
              borderRadius: '12px', marginBottom: '4px'
            }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#d8b4fe' }}>
                {selectedIds.length} camera(s) selected
              </span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => handleBatchActive(true)}
                  disabled={loading}
                  className="batchBtn start"
                  style={{ padding: '6px 12px', fontSize: '0.78rem', background: 'rgba(52, 211, 153, 0.15)', color: '#34d399', borderColor: 'rgba(52, 211, 153, 0.3)' }}
                >
                  Enable Active
                </button>
                <button
                  onClick={() => handleBatchActive(false)}
                  disabled={loading}
                  className="batchBtn"
                  style={{ padding: '6px 12px', fontSize: '0.78rem', background: 'rgba(239, 68, 68, 0.15)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                >
                  Disable Ingress
                </button>
                <button
                  onClick={handleBatchDelete}
                  disabled={loading}
                  className="batchBtn"
                  style={{ padding: '6px 12px', fontSize: '0.78rem', background: 'rgba(239, 68, 68, 0.25)', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.4)' }}
                >
                  Delete Selected
                </button>
                <button
                  onClick={() => setSelectedIds([])}
                  className="batchBtn"
                  style={{ padding: '6px 12px', fontSize: '0.78rem' }}
                >
                  Clear Selection
                </button>
              </div>
            </div>
          )}

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
                const streamIdVal = stream?.stream_id
                const isChecked = streamIdVal ? selectedIds.includes(streamIdVal) : false
                
                return (
                  <div 
                    key={cam.id} 
                    style={{ 
                      padding: '16px 20px', 
                      background: isChecked ? 'rgba(168, 85, 247, 0.05)' : 'rgba(15, 23, 42, 0.3)', 
                      border: isChecked ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid rgba(255,255,255,0.05)', 
                      borderRadius: '16px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      {/* Checkbox column */}
                      {streamIdVal && (
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggleSelect(streamIdVal)}
                          style={{
                            width: '16px',
                            height: '16px',
                            cursor: 'pointer',
                            accentColor: '#a855f7'
                          }}
                        />
                      )}
                      
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
                          {(() => {
                            const isEdge = !cam.rtsp_url || cam.rtsp_url.trim() === "" || !cam.rtsp_url.trim().toLowerCase().startsWith("rtsp://");
                            return (
                              <span style={{
                                padding: '2px 8px', borderRadius: '8px', fontSize: '0.68rem', fontWeight: 600,
                                background: isEdge ? 'rgba(168, 85, 247, 0.15)' : 'rgba(59, 130, 246, 0.12)',
                                color: isEdge ? '#c084fc' : '#60a5fa',
                                border: `1px solid ${isEdge ? 'rgba(168, 85, 247, 0.2)' : 'rgba(59, 130, 246, 0.2)'}`
                              }}>
                                {isEdge ? 'Edge Push' : 'RTSP Ingress'}
                              </span>
                            );
                          })()}
                        </div>
                        <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '0.76rem', color: '#94a3b8' }}>
                          <span>Make: {cam.make || 'Generic'}</span>
                          <span>•</span>
                          <span>Stream ID: <code style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{stream?.stream_id || '—'}</code></span>
                          <span>•</span>
                          <span>Ingress URL: <code style={{ fontFamily: 'monospace' }}>{stream?.stream_url || '—'}</code></span>
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
                        onClick={() => handleCloneClick(cam)}
                        className="batchBtn"
                        title="Clone / Duplicate Camera Settings"
                        style={{ padding: '8px', minWidth: 'auto', background: 'rgba(168,85,247,0.06)', borderColor: 'rgba(168,85,247,0.15)', color: '#d8b4fe' }}
                      >
                        <Copy size={16} />
                      </button>
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

