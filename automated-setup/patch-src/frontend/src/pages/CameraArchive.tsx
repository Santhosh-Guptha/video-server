import { useEffect, useRef, useState } from 'react'
import type { Camera } from '../types'
import { CameraArchiveSettings, type ArchiveSnapshot } from './CameraArchiveSettings'
import { controlApi as api } from '../lib/controlApi'

export function CameraArchive({ cameras }: { cameras: Camera[] }) {
  const [cameraId, setCameraId] = useState('')
  const [start, setStart] = useState('')
  const [minutes, setMinutes] = useState(5)
  const [src, setSrc] = useState('')
  const [message, setMessage] = useState('')
  const [configuration, setConfiguration] = useState<ArchiveSnapshot | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const camera = cameras.find(item => item.id === cameraId)
  const supported = !!configuration?.effective_enabled && !!configuration?.adapter_available
  const maximum = configuration?.settings.max_minutes || 15
  useEffect(() => {
    let active = true
    setConfiguration(null)
    if (cameraId) api(`/cameras/${encodeURIComponent(cameraId)}/archive`).then(value => { if (active) setConfiguration(value) }).catch(e => { if (active) setMessage(e.message) })
    return () => { active = false }
  }, [cameraId])
  useEffect(() => {
    const element = video.current
    return () => { if (element) { element.pause(); element.removeAttribute('src'); element.load() } }
  }, [])
  function stop() {
    if (video.current) { video.current.pause(); video.current.removeAttribute('src'); video.current.load() }
    setSrc(''); setMessage('Stopped. Camera request released.')
  }
  function url(download = false) {
    const timestamp = new Date(start).getTime() / 1000
    if (!camera || !supported || !Number.isFinite(timestamp) || minutes < 1 || minutes > maximum) {
      setMessage(`Select an enabled, supported camera and a duration between 1 and ${maximum} minutes.`); return ''
    }
    if (timestamp + minutes * 60 > Date.now() / 1000) { setMessage('Choose an interval that has already ended.'); return '' }
    return '/api/recordings/sd-card/download?' + new URLSearchParams({stream_id: camera.stream_id, source: 'camera', disposition: download ? 'attachment' : 'inline', start_ts: String(timestamp), end_ts: String(timestamp + minutes * 60)})
  }
  return <section className="control-panel">
    <h2>Camera / NVR archive</h2>
    <p>Request footage from device storage. Server recordings are never used and this request does not save a server recording.</p>
    <label>Camera <select value={cameraId} onChange={e => { stop(); setCameraId(e.target.value) }}>
      <option value="">Select camera</option>{cameras.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>
    {camera && <CameraArchiveSettings key={camera.id} cameraId={camera.id} onSaved={value => { stop(); setConfiguration(value) }} />}
    {configuration && <p>Saved clip limit: {maximum} minutes. Effective archive access: {configuration.effective_enabled ? 'enabled' : 'blocked by camera/server policy'}.</p>}
    {camera && <p>{supported ? 'A manufacturer playback adapter is available. Device archive support and available dates have not been verified.' : 'Archive playback is not implemented for this manufacturer. Live RTSP access alone is insufficient.'}</p>}
    <div className="control-actions">
      <label>Start time (this device’s local time) <input type="datetime-local" value={start} onChange={e => { stop(); setStart(e.target.value) }} /></label>
      <label>Minutes <input type="number" min="1" max={maximum} value={minutes} onChange={e => { stop(); setMinutes(Number(e.target.value)) }} /></label>
      <button disabled={!supported} onClick={() => { const next = url(); if (next) { stop(); setSrc(next); setMessage('Requesting camera recording…') } }}>Play from camera</button>
      <button disabled={!src} onClick={stop}>Stop</button>
      <button disabled={!supported} onClick={() => { const next = url(true); if (next) { stop(); const link = document.createElement('a'); link.href = next; link.download = 'camera-archive.mp4'; link.click(); setMessage('Camera clip download requested. Playback stopped to avoid a second request.') } }}>Download clip</button>
    </div>
    <p role="status">{message}</p>
    <video ref={video} src={src || undefined} controls autoPlay playsInline style={{width: '100%', maxHeight: '65vh', background: '#000'}} onPlaying={() => setMessage('Playing camera archive.')} onEnded={() => { stop(); setMessage('Requested interval finished.') }} onError={() => { if (src) setMessage('Playback failed: the interval may be absent, the camera may be busy, or its codec/adapter may be incompatible. Try a shorter interval or download the clip.') }} />
    <p>To jump to another time, stop and request a new start time. Archive availability search, audio and universal browser codec conversion are not implemented here.</p>
  </section>
}
