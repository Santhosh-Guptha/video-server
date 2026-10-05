import { useEffect, useRef, useState } from 'react'
import type { Camera } from '../types'

export function CameraArchive({ cameras }: { cameras: Camera[] }) {
  const [cameraId, setCameraId] = useState('')
  const [start, setStart] = useState('')
  const [minutes, setMinutes] = useState(5)
  const [src, setSrc] = useState('')
  const [message, setMessage] = useState('')
  const [adapter, setAdapter] = useState('configured')
  const video = useRef<HTMLVideoElement>(null)
  const camera = cameras.find(item => item.id === cameraId)
  const make = (camera?.make || '').toLowerCase().replace(/[- ]/g, '')
  const supported = adapter === 'unv' || ['unv', 'uniview'].includes(make)
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
    if (!camera || !supported || !Number.isFinite(timestamp) || minutes < 1 || minutes > 15) {
      setMessage('Select a supported camera, start time and duration between 1 and 15 minutes.'); return ''
    }
    if (timestamp + minutes * 60 > Date.now() / 1000) { setMessage('Choose an interval that has already ended.'); return '' }
    return '/api/recordings/sd-card/download?' + new URLSearchParams({stream_id: camera.stream_id, source: 'camera', adapter, disposition: download ? 'attachment' : 'inline', start_ts: String(timestamp), end_ts: String(timestamp + minutes * 60)})
  }
  return <section className="control-panel">
    <h2>Camera / NVR archive</h2>
    <p>Request footage from device storage. Server recordings are never used and this request does not save a server recording.</p>
    <label>Camera <select value={cameraId} onChange={e => { stop(); setCameraId(e.target.value); setAdapter('configured') }}>
      <option value="">Select camera</option>{cameras.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select></label>
    <label>Archive adapter <select value={adapter} onChange={e => { stop(); setAdapter(e.target.value) }}><option value="configured">Use configured manufacturer</option><option value="unv">UNV / Uniview (explicit selection)</option></select></label>
    <p>Select UNV only when the device uses Uniview archive URLs. This choice applies to this request and does not change camera configuration.</p>
    {camera && <p>{supported ? 'A manufacturer playback adapter is available. Device archive support and available dates have not been verified.' : 'Archive playback is not implemented for this manufacturer. Live RTSP access alone is insufficient.'}</p>}
    <div className="control-actions">
      <label>Start time (this device’s local time) <input type="datetime-local" value={start} onChange={e => { stop(); setStart(e.target.value) }} /></label>
      <label>Minutes <input type="number" min="1" max="15" value={minutes} onChange={e => { stop(); setMinutes(Number(e.target.value)) }} /></label>
      <button disabled={!supported} onClick={() => { const next = url(); if (next) { stop(); setSrc(next); setMessage('Requesting camera recording…') } }}>Play from camera</button>
      <button disabled={!src} onClick={stop}>Stop</button>
      <button disabled={!supported} onClick={() => { const next = url(true); if (next) { stop(); const link = document.createElement('a'); link.href = next; link.download = 'camera-archive.mp4'; link.click(); setMessage('Camera clip download requested. Playback stopped to avoid a second request.') } }}>Download clip</button>
    </div>
    <p role="status">{message}</p>
    <video ref={video} src={src || undefined} controls autoPlay playsInline style={{width: '100%', maxHeight: '65vh', background: '#000'}} onPlaying={() => setMessage('Playing camera archive.')} onEnded={() => { stop(); setMessage('Requested interval finished.') }} onError={() => { if (src) setMessage('Playback failed: the interval may be absent, the camera may be busy, or its codec/adapter may be incompatible. Try a shorter interval or download the clip.') }} />
    <p>To jump to another time, stop and request a new start time. Archive availability search, audio and universal browser codec conversion are not implemented here.</p>
  </section>
}
