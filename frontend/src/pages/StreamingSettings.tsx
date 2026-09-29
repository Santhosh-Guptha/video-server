import { useEffect, useState } from 'react'

type Values = {
  grid_view_profile: string; focus_view_profile: string; playback_profile: string;
  webrtc_stall_timeout_seconds: number; webrtc_connection_timeout_seconds: number;
  max_active_transcoders: number;
  webrtc_jitter_buffer_ms: number;
  rtsp_connections_per_endpoint: number;
  default_retention_days: number;
}
type Configuration = {
  settings: Values; upstream_url: string; turn_configured: boolean;
  recording: { hd_only: boolean; retention_days: number; segment_seconds: number };
}

export function StreamingSettings() {
  const [capacity, setCapacity] = useState<{ shared_ingests: number; blocked_paths: string[]; endpoints: { endpoint: string; reserved_ingests: number; temporary_connections: number; at_capacity: boolean }[] } | null>(null)
  const refreshCapacity = () => fetch('/api/settings/streaming/rtsp-capacity').then(async r => {
    if (r.ok) setCapacity(await r.json())
  }).catch(() => {})
  const [data, setData] = useState<Configuration | null>(null)
  const [values, setValues] = useState<Values | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    refreshCapacity()
    let disposed = false
    fetch('/api/settings/streaming').then(async response => {
      if (!response.ok) throw new Error('Could not load streaming settings')
      const result: Configuration = await response.json()
      if (!disposed) { setData(result); setValues(result.settings) }
    }).catch(e => { if (!disposed) setError(e.message) })
    return () => { disposed = true }
  }, [])
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch('/api/settings/streaming', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values),
      })
      if (!response.ok) throw new Error(response.status === 422 ? 'Check the allowed values before saving.' : 'Settings could not be saved.')
      const result: Configuration = await response.json()
      setData(result); setValues(result.settings)
      refreshCapacity()
      window.dispatchEvent(new Event('streaming-settings-changed'))
      setMessage('Saved. Settings persist after restart and apply when a stream is opened again.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Save failed') }
    finally { setBusy(false) }
  }
  const control = { padding: '10px', background: '#111827', color: '#f8fafc', border: '1px solid #475569', borderRadius: 6 }
  return <section style={{ padding: 24, maxWidth: 900, color: '#e2e8f0' }}>
    <h2>Streaming Settings</h2>
    <p>Choose the highest available source quality, and control recovery when live video stops progressing.</p>
    {error && <p role="alert" style={{ color: '#fca5a5' }}>{error}</p>}
    {message && <p role="status" style={{ color: '#86efac' }}>{message}</p>}
    {!values || !data ? <p>Loading configuration…</p> : <>
      <form onSubmit={save} style={{ display: 'grid', gap: 18 }}>
        {([['grid_view_profile', 'Camera wall quality'], ['focus_view_profile', 'Single-camera quality'], ['playback_profile', 'Playback quality']] as const).map(([key, label]) =>
          <label key={key} style={{ display: 'grid', gap: 6 }}>{label}
            <select style={control} value={values[key]} onChange={e => setValues({ ...values, [key]: e.target.value })}>
              <option value="HD">HD — highest configured main stream</option><option value="NORMAL">Normal — substream</option><option value="MOBILE">Mobile — mobile stream</option>
            </select>
          </label>)}
        {([['webrtc_stall_timeout_seconds', 'Frozen video recovery (seconds)', 4, 60], ['webrtc_connection_timeout_seconds', 'Connection timeout (seconds)', 10, 60], ['max_active_transcoders', 'Maximum simultaneous codec conversions', 1, 10]] as const).map(([key, label, min, max]) =>
          <label key={key} style={{ display: 'grid', gap: 6 }}>{label}
            <input required type="number" style={control} min={min} max={max} step={1} value={values[key]} onChange={e => setValues({ ...values, [key]: e.target.valueAsNumber })} />
          </label>)}
        <label style={{ display: 'grid', gap: 6 }}>Live smoothing buffer target (milliseconds)
          <input required type="number" style={control} min={0} max={1000} step={1} value={values.webrtc_jitter_buffer_ms} onChange={e => setValues({ ...values, webrtc_jitter_buffer_ms: e.target.valueAsNumber })} />
        </label>
        <p>Start at 100 ms. A larger target can smooth uneven packet arrival but adds delay. This is a browser hint, not a latency limit; unsupported browsers use their automatic buffer. Resolution and recording quality are unchanged.</p>
        <label style={{ display: 'grid', gap: 6 }}>RTSP connection budget per camera/NVR endpoint
          <input required type="number" style={control} min={1} max={128} step={1} value={values.rtsp_connections_per_endpoint} onChange={e => setValues({ ...values, rtsp_connections_per_endpoint: e.target.valueAsNumber })} />
        </label>
        <p>Live viewers share the camera ingest. Each configured source reserves one slot by host and RTSP port, including while reconnecting. Probes and camera playback use spare slots; extra requests are deferred or rejected. Existing sources above a lowered limit keep running. Set this budget to the device's supported capacity, allowing headroom for other applications.</p>
        <label style={{ display: 'grid', gap: 6 }}>Maximum recording retention (days)
          <input required type="number" style={control} min={1} max={365} step={1} value={values.default_retention_days} onChange={e => setValues({ ...values, default_retention_days: e.target.valueAsNumber })} />
        </label>
        <p>Recordings keep the camera's original HD encoding. Shorter retention saves disk space without reducing image quality. A camera's shorter archive period still applies. Older recordings are removed by the periodic cleanup after you save this setting.</p>
        <p>HD preserves the camera's actual resolution. If its main stream is unavailable, the wall labels its lower-quality fallback. Conversion capacity depends on this server's CPU; native streams do not use a conversion slot.</p>
        <button type="submit" disabled={busy} className="refreshBtn">{busy ? 'Saving…' : 'Save streaming settings'}</button>
      </form>
      <h3>RTSP capacity</h3>
      <button type="button" onClick={refreshCapacity}>Refresh RTSP capacity</button>
      {capacity && <>
        <p>{capacity.shared_ingests} shared camera sources · {capacity.blocked_paths.length} paths waiting for capacity. Camera playback and probes also share a two-connection background budget to protect live viewing.</p>
        <p>Reservations prevent this application's connections from competing. They cannot lock out external clients or prove the camera's hardware limit. This deployment uses one backend process.</p>
        {capacity.endpoints.some(e => e.at_capacity) && <table><thead><tr><th>Endpoint at capacity</th><th>Reserved sources</th><th>Temporary connections</th></tr></thead>
          <tbody>{capacity.endpoints.filter(e => e.at_capacity).map(e => <tr key={e.endpoint}><td>{e.endpoint}</td><td>{e.reserved_ingests}</td><td>{e.temporary_connections}</td></tr>)}</tbody></table>}
      </>}
      <h3>Connected services</h3>
      <p>Camera configuration upstream: <a href={data.upstream_url} target="_blank" rel="noreferrer">{data.upstream_url}</a></p>
      <p>TURN: {data.turn_configured ? 'Configured as a connection fallback' : 'Not configured'}</p>
      <p>Recordings: {data.recording.hd_only ? 'HD profile' : 'Multiple profiles'} · {data.recording.segment_seconds}-second segments · up to {data.recording.retention_days}-day retention</p>
      <p>Camera-side starting point: native resolution, a one-second keyframe interval, 15–25 FPS and a bitrate supported by the network. H.264 without B-frames gives broader browser support. These settings do not modify remote camera encoders.</p>
    </>}
  </section>
}
