import { useEffect, useState } from 'react'
import { controlApi as api } from '../lib/controlApi'

export type ArchiveConfig = { enabled: boolean; adapter: 'configured' | 'unv' | 'hikvision'; stream_id: string; max_minutes: number; first_data_timeout: number; idle_timeout: number }
export type ArchiveSnapshot = { revision: number; settings: ArchiveConfig; effective_enabled: boolean; server_enabled: boolean; adapter_available: boolean; adapter_error?: string; last_failure?: { time: number; start_ts: number; end_ts: number; detail: string }; streams: {id: string; profile: string; resolution: string}[] }

export function CameraArchiveSettings({ cameraId, onSaved }: { cameraId: string; onSaved?: (value: ArchiveSnapshot) => void }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<ArchiveSnapshot | null>(null)
  const [draft, setDraft] = useState<ArchiveConfig | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    if (!open) return
    let active = true
    setData(null); setDraft(null); setMessage(''); setBusy(true)
    api(`/cameras/${encodeURIComponent(cameraId)}/archive`).then(value => { if (active) { setData(value); setDraft(value.settings) } }).catch(e => { if (active) setMessage(e.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [cameraId, open, reload])
  return <details className="camera-organizer" onToggle={e => setOpen(e.currentTarget.open)}><summary>Camera archive configuration</summary>
    <p>Saved for this camera and retained across upstream synchronization. Changes apply to new archive requests.</p>
    {data && draft && <>
      <p>Effective access: <strong>{data.effective_enabled ? 'Enabled' : 'Blocked'}</strong> · Server archive feature: {data.server_enabled ? 'Enabled' : 'Disabled'} · Adapter: {data.adapter_available ? 'Available, device unverified' : 'Not supported / not configured'}</p>
      {data.adapter_error && <p role="alert">{data.adapter_error}</p>}
      <label><input type="checkbox" checked={draft.enabled} onChange={e => setDraft({...draft, enabled: e.target.checked})} /> Allow camera archive requests</label>
      <label>Adapter<select value={draft.adapter} onChange={e => setDraft({...draft, adapter: e.target.value as ArchiveConfig['adapter']})}><option value="configured">Use camera manufacturer</option><option value="unv">UNV / Uniview</option><option value="hikvision">Hikvision / compatible tracks API</option></select></label>
      <label>Archive stream profile<select value={draft.stream_id} onChange={e => setDraft({...draft, stream_id: e.target.value})}><option value="">Use requested stream</option>{draft.stream_id && !data.streams.some(s => s.id === draft.stream_id) && <option value={draft.stream_id}>Unavailable: {draft.stream_id}</option>}{data.streams.map(stream => <option key={stream.id} value={stream.id}>{stream.profile} · {stream.resolution} · {stream.id}</option>)}</select></label>
      {([['max_minutes', 'Maximum clip minutes', 1, 15], ['first_data_timeout', 'First data timeout (seconds)', 5, 60], ['idle_timeout', 'Idle timeout (seconds)', 5, 60]] as const).map(([key, label, min, max]) => <label key={key}>{label}<input type="number" min={min} max={max} step="1" value={draft[key]} onChange={e => setDraft({...draft, [key]: Number(e.target.value)})} /></label>)}
      <p>These settings control archive retrieval. Live and server recording may stay off. Ignore policy, full server pause and global connection limits still apply. This does not reconfigure device storage or its encoder.</p>
      <button disabled={busy} onClick={async () => { setBusy(true); setMessage(''); try { const value = await api(`/cameras/${encodeURIComponent(cameraId)}/archive`, 'PUT', {...draft, revision: data.revision}); setData(value); setDraft(value.settings); setMessage('Saved. New requests use these settings.'); onSaved?.(value) } catch (e: any) { setMessage(e.message) } finally { setBusy(false) } }}>Save camera archive settings</button>
    </>}
    <button disabled={busy} onClick={() => setReload(value => value + 1)}>Reload saved settings</button>
    <p role="status">{busy ? 'Loading / saving…' : message}</p>
  </details>
}
