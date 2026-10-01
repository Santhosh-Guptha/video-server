import { useEffect, useState } from 'react'
import type { Camera } from '../types'
import { CameraManagement } from './CameraManagement'
import { StreamingSettings } from './StreamingSettings'
import './ServerControl.css'
import { controlApi as api, downloadCsv } from '../lib/controlApi'
import { FleetActions, CameraOrganizer, DiagnosticsPanel, ActivityPanel } from './FleetTools'

type Policy = { ignored: boolean; live: boolean; recording: boolean; retention_days: number | null; site?: string; tags?: string[]; notes?: string; favorite?: boolean }
type Row = { id: string; name: string; source: string; active: boolean; policy: Policy; effective_live: boolean; effective_recording: boolean; streams: { id: string; profile: string; resolution: string; codec: string; status: string; segments: number }[] }
type Snapshot = { revision: number; checked_at: number; runtime: { status: string }; server: { live: boolean; recording: boolean; upstream_url: string }; disk: { free: number; total: number }; cameras: Row[] }
export function ServerControl({ cameras, onRefresh }: { cameras: Camera[]; onRefresh: () => void }) {
  const [data, setData] = useState<Snapshot | null>(null)
  const [tab, setTab] = useState('operations')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [siteFilter, setSiteFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [checked, setChecked] = useState<string[]>([])
  const [autoRefresh, setAutoRefresh] = useState(false)
  useEffect(() => setPage(1), [search, filter, siteFilter])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [url, setUrl] = useState('')
  const [selected, setSelected] = useState('all')
  const [before, setBefore] = useState('')
  const [preview, setPreview] = useState<{ cameras: number; segments: number; before: number; message: string } | null>(null)
  const [confirm, setConfirm] = useState(false)
  const load = async () => { const next = await api(); setData(next); setUrl(current => !current || current === data?.server.upstream_url ? next.server.upstream_url : current) }
  useEffect(() => {
    if (!autoRefresh || busy || tab !== 'operations') return
    const timer = window.setInterval(() => { api().then(setData).catch(e => setError(e.message)) }, 30000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, busy, tab])
  useEffect(() => { load().catch(e => setError(e.message)) }, [])
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setMessage('')
    try { await action() } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const server = (changes: Partial<Snapshot['server']>) => run(async () => {
    setData(await api('/server', 'PUT', { ...data!.server, ...changes, revision: data!.revision })); setMessage('Server policy saved and applied.'); onRefresh()
  })
  const camera = (row: Row, changes: Partial<Policy>) => run(async () => {
    const { ignored, live, recording, retention_days } = row.policy
    setData(await api('/cameras/' + row.id, 'PUT', { ignored, live, recording, retention_days, ...changes, revision: data!.revision })); setMessage(`${row.name}: controls applied.`); onRefresh()
  })
  const rows = data?.cameras.filter(c => {
    const matchesSearch = (c.name + ' ' + (c.policy.site || '') + ' ' + (c.policy.tags || []).join(' ') + ' ' + c.streams.map(s => s.id).join(' ')).toLowerCase().includes(search.toLowerCase())
    const matchesFilter = filter === 'all' || (filter === 'ignored' && c.policy.ignored) || (filter === 'favorites' && c.policy.favorite) || (filter === 'upstream' && c.source === 'UPSTREAM') || (filter === 'local' && c.source === 'LOCAL') || (filter === 'recording_off' && !c.effective_recording)
    return matchesSearch && matchesFilter && (siteFilter === 'all' || c.policy.site === siteFilter)
  }) || []
  const pages = Math.max(1, Math.ceil(rows.length / 25))
  const currentPage = Math.min(page, pages)
  const visibleRows = rows.slice((currentPage - 1) * 25, currentPage * 25)
  const sites = [...new Set(data?.cameras.map(c => c.policy.site).filter(Boolean) || [])]
  const update = (next: Snapshot) => { setData(next); onRefresh() }
  return <section className="server-control">
    <header><div><p className="eyebrow">OPERATIONS</p><h1>Server control</h1><p>One place to manage cameras, live access, recording and storage.</p></div><button disabled={busy} onClick={() => run(load)}>Refresh status</button></header>
    <nav aria-label="Server control sections">{[['operations', 'Live & recording'], ['sources', 'Camera sources & configuration'], ['storage', 'Storage & deletion'], ['quality', 'Streaming & retention defaults'], ['diagnostics', 'Diagnostics'], ['activity', 'Activity & backup']].map(([key, title]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{title}</button>)}</nav>
    {error && <p role="alert" className="control-error">{error}</p>}{message && <p role="status" className="control-success">{message}</p>}
    {!data ? <p>{error ? 'Controls could not be loaded. Use Refresh status to try again.' : 'Loading controls…'}</p> : <>
      <p className="snapshot-time">Updated {new Date(data.checked_at * 1000).toLocaleTimeString()} · Policy revision {data.revision}{data.runtime.status === 'failed' && <span className="status-warning"> · Changes saved but not fully applied — see Diagnostics</span>}</p>
      <div className="control-stats"><div><strong>{data.cameras.length}</strong><span>Configured cameras</span></div><div><strong>{data.cameras.filter(c => c.effective_live).length}</strong><span>Live permitted</span></div><div><strong>{data.cameras.filter(c => c.effective_recording).length}</strong><span>Recording permitted</span></div><div><strong>{(data.disk.free / 1024 ** 3).toFixed(1)} GiB</strong><span>Free inside WSL</span></div></div>
      {tab === 'operations' && <>
        <div className="control-panel"><h2>Server switches</h2><p>Stopping live disconnects viewers. Stopping recording also stops recovery. Stop both to suspend camera connections; individual camera choices are preserved.</p><div className="control-actions"><button disabled={busy} onClick={() => server({ live: !data.server.live })}>{data.server.live ? 'Stop all live viewing' : 'Enable live viewing'}</button><button disabled={busy} onClick={() => server({ recording: !data.server.recording })}>{data.server.recording ? 'Stop all recording' : 'Enable recording'}</button><button disabled={busy} onClick={() => server({ live: false, recording: false })}>Pause entire server</button></div></div>
        <div className="fleet-filters"><label className="control-search">Find a camera<input placeholder="Name, ID, site or tag" value={search} onChange={e => setSearch(e.target.value)} /></label><label>Show<select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All cameras</option><option value="favorites">Favorites</option><option value="ignored">Ignored</option><option value="recording_off">Recording blocked</option><option value="upstream">Upstream cameras</option><option value="local">Manual cameras</option></select></label><label>Site<select value={siteFilter} onChange={e => setSiteFilter(e.target.value)}><option value="all">All sites</option>{sites.map(site => <option key={site} value={site}>{site}</option>)}</select></label><label><input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} /> Refresh status every 30 seconds</label></div>
        <FleetActions ids={checked} revision={data.revision} busy={busy} onClear={() => setChecked([])} onApply={payload => run(async () => { update(await api('/bulk', 'POST', payload)); setMessage('Bulk camera policy applied.'); setChecked([]) })} />
        <div className="pagination"><button disabled={!rows.length} onClick={() => downloadCsv('camera-inventory.csv', [['Name', 'Camera ID', 'Source', 'Site', 'Tags', 'Live permitted', 'Recording permitted', 'Ignored', 'Retention days'], ...rows.map(c => [c.name, c.id, c.source, c.policy.site || '', (c.policy.tags || []).join('; '), c.effective_live, c.effective_recording, c.policy.ignored, c.policy.retention_days || 'Default'])])}>Export filtered inventory</button><span>{rows.length} matching cameras · page {currentPage} of {pages}</span><button disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}>Previous page</button><button disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}>Next page</button></div>
        <p>“Ignore” blocks live, recording, probes and recovery until you turn it off. Upstream sync keeps these operator choices. Recording follows the configured profile policy.</p>
        <div className="control-table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select visible cameras" checked={visibleRows.length > 0 && visibleRows.every(c => checked.includes(c.id))} onChange={e => setChecked(e.target.checked ? [...new Set([...checked, ...visibleRows.map(c => c.id)])] : checked.filter(id => !visibleRows.some(c => c.id === id)))} /></th><th>Camera / profiles</th><th>Live</th><th>Recording</th><th>Ignore</th><th>Retention</th></tr></thead><tbody>{visibleRows.map(row => <tr key={row.id}>
          <td><input type="checkbox" aria-label={`Select ${row.name}`} checked={checked.includes(row.id)} onChange={e => setChecked(e.target.checked ? [...checked, row.id] : checked.filter(id => id !== row.id))} /></td>
          <td><strong>{row.policy.favorite ? '★ ' : ''}{row.name}</strong><small>{row.policy.site}{row.policy.tags?.length ? ' · ' + row.policy.tags.join(', ') : ''}</small><small>{row.source} · {row.active ? 'Source enabled' : 'Source disabled'}</small>{row.streams.map(s => <small key={s.id}>{s.id} · {s.resolution} · {s.codec} · {s.status}</small>)}<CameraOrganizer camera={row} revision={data.revision} busy={busy} onUpdated={update} /></td>
          <td><button disabled={busy || row.policy.ignored} aria-label={`${row.name} live ${row.policy.live ? 'stop' : 'start'}`} onClick={() => camera(row, { live: !row.policy.live })}>{row.policy.live ? 'Stop live' : 'Start live'}</button><small>{row.effective_live ? 'Permitted' : 'Blocked'}</small></td>
          <td><button disabled={busy || row.policy.ignored} aria-label={`${row.name} recording ${row.policy.recording ? 'stop' : 'start'}`} onClick={() => camera(row, { recording: !row.policy.recording })}>{row.policy.recording ? 'Stop recording' : 'Start recording'}</button><small>{row.effective_recording ? 'Permitted' : 'Blocked'}</small></td>
          <td><button disabled={busy} aria-pressed={row.policy.ignored} onClick={() => camera(row, { ignored: !row.policy.ignored })}>{row.policy.ignored ? 'Unignore' : 'Ignore camera'}</button></td>
          <td><Retention key={row.id + ':' + row.policy.retention_days} value={row.policy.retention_days} disabled={busy} onSave={value => camera(row, { retention_days: value })} /></td>
        </tr>)}</tbody></table>{!rows.length && <p>No cameras match your search.</p>}</div>
      </>}
      {tab === 'sources' && <><div className="control-panel"><h2>Camera configuration URL</h2><label>Upstream API<input type="url" value={url} onChange={e => setUrl(e.target.value)} /></label><button disabled={busy || !url} onClick={() => server({ upstream_url: url })}>Save source URL</button><p>The next Sync Cameras imports this URL. Local camera editing and source selection are below.</p></div><CameraManagement cameras={cameras} onRefresh={onRefresh} /></>}
      {tab === 'quality' && <StreamingSettings />}
      {tab === 'diagnostics' && <DiagnosticsPanel onUpdated={update} />}
      {tab === 'activity' && <ActivityPanel revision={data.revision} onUpdated={update} />}
      {tab === 'storage' && <div className="control-panel"><h2>Delete recordings</h2><p>Stop recording for the selected camera(s) first. Preview the scope, then explicitly confirm. Active or recently completed files are protected. Deleted history will not be downloaded again by recovery.</p><label>Camera<select value={selected} onChange={e => { setSelected(e.target.value); setPreview(null); setConfirm(false) }}><option value="all">All cameras</option>{data.cameras.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Delete recordings ending before (your local time)<input type="datetime-local" value={before} onChange={e => { setBefore(e.target.value); setPreview(null); setConfirm(false) }} /></label><button disabled={busy || !before} onClick={() => run(async () => { setPreview(await api('/recordings/preview', 'POST', { camera_id: selected, before: new Date(before).getTime() / 1000 })); setConfirm(false) })}>Preview deletion</button>
        {preview && <div className="delete-preview"><strong>{preview.segments} recording segments across {preview.cameras} cameras</strong><p>{preview.message}</p><label><input type="checkbox" checked={confirm} onChange={e => setConfirm(e.target.checked)} /> I understand this permanently deletes the selected recordings.</label><button className="danger" disabled={busy || !confirm || !preview.segments} onClick={() => run(async () => { const result = await api('/recordings/delete', 'POST', { camera_id: selected, before: preview.before, confirm: true }); setMessage(`Deleted ${result.deleted} segments; ${(result.bytes_freed / 1024 ** 3).toFixed(2)} GiB freed; ${result.failed} files could not be deleted.`); setPreview(null); setConfirm(false); await load() })}>Permanently delete recordings</button></div>}
        <p>Retention and storage quota are under “Streaming & retention defaults”; per-camera retention is under “Live & recording.” Freeing Linux files does not automatically shrink the Windows WSL disk file.</p></div>}
    </>}
  </section>
}

function Retention({ value, disabled, onSave }: { value: number | null; disabled: boolean; onSave: (value: number | null) => void }) {
  const [days, setDays] = useState(value?.toString() || '')
  return <div><input aria-label="Retention days" type="number" min="1" max="365" placeholder="Default" value={days} onChange={e => setDays(e.target.value)} /><small>Days · blank uses server default</small><button disabled={disabled || (!!days && (!Number.isInteger(Number(days)) || +days < 1 || +days > 365))} onClick={() => onSave(days ? Number(days) : null)}>Save retention</button></div>
}
