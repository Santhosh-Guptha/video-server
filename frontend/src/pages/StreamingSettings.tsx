import { useEffect, useState } from 'react'

type Values = {
  grid_view_profile: string; focus_view_profile: string; playback_profile: string;
  webrtc_stall_timeout_seconds: number; webrtc_connection_timeout_seconds: number;
  max_active_transcoders: number;
  default_retention_days: number;
}
type Configuration = {
  settings: Values; upstream_url: string; turn_configured: boolean;
  recording: { hd_only: boolean; retention_days: number; segment_seconds: number };
}

export function StreamingSettings() {
  const [data, setData] = useState<Configuration | null>(null)
  const [values, setValues] = useState<Values | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
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
        <label style={{ display: 'grid', gap: 6 }}>Maximum recording retention (days)
          <input required type="number" style={control} min={1} max={365} step={1} value={values.default_retention_days} onChange={e => setValues({ ...values, default_retention_days: e.target.valueAsNumber })} />
        </label>
        <p>Recordings keep the camera's original HD encoding. Shorter retention saves disk space without reducing image quality. A camera's shorter archive period still applies. Older recordings are removed by the periodic cleanup after you save this setting.</p>
        <p>HD preserves the camera's actual resolution. If its main stream is unavailable, the wall labels its lower-quality fallback. Conversion capacity depends on this server's CPU; native streams do not use a conversion slot.</p>
        <button type="submit" disabled={busy} className="refreshBtn">{busy ? 'Saving…' : 'Save streaming settings'}</button>
      </form>
      <h3>Connected services</h3>
      <p>Camera configuration upstream: <a href={data.upstream_url} target="_blank" rel="noreferrer">{data.upstream_url}</a></p>
      <p>TURN: {data.turn_configured ? 'Configured as a connection fallback' : 'Not configured'}</p>
      <p>Recordings: {data.recording.hd_only ? 'HD profile' : 'Multiple profiles'} · {data.recording.segment_seconds}-second segments · up to {data.recording.retention_days}-day retention</p>
      <p>Camera-side starting point: native resolution, a one-second keyframe interval, 15–25 FPS and a bitrate supported by the network. H.264 without B-frames gives broader browser support. These settings do not modify remote camera encoders.</p>
    </>}
  </section>
}
