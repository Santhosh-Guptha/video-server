import { useEffect, useState } from 'react'
import { controlApi as api, downloadJson } from '../lib/controlApi'

type Metadata = { site?: string; tags?: string[]; notes?: string; favorite?: boolean }
type Camera = { id: string; name: string; policy: Metadata }
const actionLabels: Record<string, string> = { live_on: 'Enable live', live_off: 'Stop live', recording_on: 'Enable recording', recording_off: 'Stop recording', ignore: 'Ignore cameras', unignore: 'Unignore cameras', retention: 'Set retention' }

export function FleetActions({ ids, revision, busy, onApply, onClear }: { ids: string[]; revision: number; busy: boolean; onApply: (payload: unknown) => Promise<void>; onClear: () => void }) {
  const [action, setAction] = useState('live_off')
  const [days, setDays] = useState('')
  const [review, setReview] = useState<{ camera_ids: string[]; action: string; retention_days: number | null; revision: number } | null>(null)
  useEffect(() => setReview(null), [ids.join('|'), action, days])
  return <div className="fleet-toolbar"><strong>{ids.length} selected</strong><select aria-label="Bulk camera action" value={action} onChange={e => setAction(e.target.value)}>{Object.entries(actionLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select>{action === 'retention' && <input aria-label="Bulk retention days" type="number" min="1" max="365" placeholder="Default retention" value={days} onChange={e => setDays(e.target.value)} />}
    <button disabled={busy || !ids.length || ids.length > 500 || (action === 'retention' && !!days && (!Number.isInteger(+days) || +days < 1 || +days > 365))} onClick={() => setReview({ camera_ids: [...ids], action, retention_days: days ? +days : null, revision })}>Review action</button><button disabled={!ids.length || busy} onClick={onClear}>Clear selection</button>
    {review && <div className="bulk-review" role="region" aria-label="Review bulk action"><strong>{actionLabels[review.action]} for {review.camera_ids.length} cameras?</strong><p>Live and recording choices are independent. Ignored cameras remain blocked until unignored. Global switches still apply.</p><button disabled={busy} onClick={async () => { await onApply(review); setReview(null) }}>Apply to selected cameras</button><button onClick={() => setReview(null)}>Cancel</button></div>}
  </div>
}

export function CameraOrganizer({ camera, revision, busy, onUpdated }: { camera: Camera; revision: number; busy: boolean; onUpdated: (value: any) => void }) {
  const [site, setSite] = useState(camera.policy.site || '')
  const [tags, setTags] = useState((camera.policy.tags || []).join(', '))
  const [notes, setNotes] = useState(camera.policy.notes || '')
  const [favorite, setFavorite] = useState(!!camera.policy.favorite)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [openedRevision, setOpenedRevision] = useState(revision)
  return <details className="camera-organizer" onToggle={e => { if (e.currentTarget.open) { setOpenedRevision(revision); setSite(camera.policy.site || ''); setTags((camera.policy.tags || []).join(', ')); setNotes(camera.policy.notes || ''); setFavorite(!!camera.policy.favorite) } }}><summary>Organize camera</summary><label>Site<input maxLength={100} value={site} onChange={e => setSite(e.target.value)} /></label><label>Tags (comma separated)<input value={tags} onChange={e => setTags(e.target.value)} /></label><label>Operator notes<textarea maxLength={1000} value={notes} onChange={e => setNotes(e.target.value)} /></label><label><input type="checkbox" checked={favorite} onChange={e => setFavorite(e.target.checked)} /> Favorite</label>{error && <p role="alert">{error}</p>}<button disabled={busy || saving} onClick={async () => { setSaving(true); setError(''); try { onUpdated(await api(`/cameras/${camera.id}/metadata`, 'PUT', { site, tags: tags.split(',').map(t => t.trim()).filter(Boolean), notes, favorite, revision: openedRevision })) } catch (e: any) { setError(e.message) } finally { setSaving(false) } }}>Save organization</button></details>
}

export function DiagnosticsPanel({ onUpdated }: { onUpdated: (value: any) => void }) {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function refresh() { setBusy(true); setError(''); try { setData(await api('/diagnostics')) } catch (e: any) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { refresh() }, [])
  return <div className="control-panel"><h2>System diagnostics</h2><p>Dependency checks and current workload. Camera reachability does not guarantee decodable video.</p><button disabled={busy} onClick={refresh}>Run checks</button>{error && <p role="alert" className="control-error">{error}</p>}{data && <><p>Checked {new Date(data.checked_at * 1000).toLocaleString()}</p><div className="diagnostic-grid"><div><h3>Media service</h3><strong className={data.media.status === 'ok' ? 'status-ok' : 'status-warning'}>{data.media.status}</strong><p>{data.media.message || `${data.media.ready_paths} ready paths / ${data.media.configured_paths} configured · ${data.media.latency_ms} ms`}</p></div><div><h3>Redis</h3><strong className={data.cache.status === 'ok' ? 'status-ok' : 'status-warning'}>{data.cache.status}</strong><p>{data.cache.message || 'Cache service responds.'}</p></div><div><h3>Video conversion</h3><strong>{data.transcoders} / {data.transcoder_limit}</strong><p>Active compatibility transcoders. {data.recovery_jobs} recovery jobs.</p></div><div><h3>Recording quota</h3><strong>{data.storage_limit_gib ? `${data.storage_limit_gib} GiB` : 'Unlimited'}</strong><p>{data.storage_limit_gib ? 'Old completed recordings are evicted at the limit.' : 'Configure a storage limit to prevent uncontrolled disk growth.'}</p></div><div><h3>TURN relay</h3><strong>{data.turn_configured ? 'Configured' : 'Not configured'}</strong><p>Configuration only; relay connectivity depends on the viewing network.</p></div><div><h3>Policy application</h3><strong>{data.runtime.status}</strong><p>Retry safely after a media service outage.</p><button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { onUpdated(await api('/reconcile', 'POST')); await refresh() } catch (e: any) { setError(e.message) } finally { setBusy(false) } }}>Retry apply</button></div></div></>}</div>
}

export function ActivityPanel({ revision, onUpdated }: { revision: number; onUpdated: (value: any) => void }) {
  const [items, setItems] = useState<any[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() { setBusy(true); setError(''); try { setItems((await api('/activity')).items) } catch (e: any) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { load() }, [])
  return <div className="control-panel"><h2>Activity history</h2><p>Latest 500 control changes and deletion outcomes. This local history does not identify individual users.</p><div className="control-actions"><button disabled={busy} onClick={load}>Refresh activity</button><button disabled={!items.length} onClick={() => downloadJson('video-server-activity.json', items)}>Download history</button><button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { downloadJson('video-server-policy-backup.json', await api('/backup')) } catch (e: any) { setError(e.message) } finally { setBusy(false) } }}>Download policy backup</button></div><p>The policy backup contains camera names, operating choices, sites and tags. Camera credentials, source URLs and notes are excluded.</p><RestorePanel revision={revision} onUpdated={onUpdated} />{error && <p role="alert" className="control-error">{error}</p>}<div className="control-table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Target</th><th>Revision</th></tr></thead><tbody>{items.map((item, i) => <tr key={i}><td>{new Date(item.time * 1000).toLocaleString()}</td><td>{item.action}</td><td>{item.target}</td><td>{item.revision}</td></tr>)}</tbody></table>{!items.length && <p>{busy ? 'Loading activity…' : 'No recorded control changes yet.'}</p>}</div></div>
}

function RestorePanel({ revision, onUpdated }: { revision: number; onUpdated: (value: any) => void }) {
  const [document, setDocument] = useState<any>(null)
  const [preview, setPreview] = useState<any>(null)
  const [reviewRevision, setReviewRevision] = useState(revision)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  return <details className="control-panel"><summary>Restore a policy backup</summary><p>Restores operating choices and organization for matching camera IDs. This does not recreate cameras or restore video files. Existing source URLs, credentials, notes and recording deletion cutoffs are preserved.</p><label>Policy JSON file<input type="file" accept=".json,application/json" disabled={busy} onChange={async e => { const file = e.target.files?.[0]; setDocument(null); setPreview(null); setConfirmed(false); setMessage(''); if (!file) return; try { if (file.size > 1024 * 1024) throw new Error('Backup must be smaller than 1 MiB.'); setDocument(JSON.parse(await file.text())) } catch (error: any) { setMessage(error.message) } }} /></label><button disabled={!document || busy} onClick={async () => { setBusy(true); setMessage(''); try { setPreview(await api('/backup/preview', 'POST', { document, revision })); setReviewRevision(revision); setConfirmed(false) } catch (error: any) { setMessage(error.message) } finally { setBusy(false) } }}>Preview restore</button>{preview && <div className="bulk-review"><strong>{preview.cameras} camera policies</strong><p>Server live: {preview.server.live ? 'enabled' : 'stopped'} · Recording: {preview.server.recording ? 'enabled' : 'stopped'}</p>{!preview.can_restore ? <p role="alert">{preview.unknown.length} camera IDs are absent from this server. Restore is blocked.</p> : <><label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> Replace these camera policies and server switches with this backup.</label><button disabled={busy || !confirmed} onClick={async () => { setBusy(true); setMessage(''); try { onUpdated(await api('/backup/restore', 'POST', { document, revision: reviewRevision, confirm: true })); setPreview(null); setConfirmed(false); setMessage('Policy backup restored and applied.') } catch (error: any) { setMessage(error.message) } finally { setBusy(false) } }}>Restore policy</button></>}</div>}{message && <p role="status">{message}</p>}</details>
}
