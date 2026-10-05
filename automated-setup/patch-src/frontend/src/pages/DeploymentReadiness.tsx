import { useEffect, useState } from 'react'
import { controlApi as api, downloadJson } from '../lib/controlApi'

type Report = {
  checked_at: number
  mode: 'onprem' | 'hosted'
  ready: boolean
  blocking_count: number
  scope: string
  checks: { id: string; status: string; title: string; detail: string }[]
}

export function DeploymentReadiness() {
  const [mode, setMode] = useState<'onprem' | 'hosted'>('onprem')
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    let active = true
    setReport(null); setError('')
    api(`/deployment-readiness?mode=${mode}`).then(value => {
      if (active) setReport(value)
    }).catch((e: Error) => { if (active) setError(e.message) })
    return () => { active = false }
  }, [mode, version])
  return <section className="control-panel" aria-label="Deployment readiness">
    <h2>Deployment readiness</h2>
    <p>Review requirements before handing this server to a customer. This does not change the deployment or interrupt cameras.</p>
    <div className="control-actions">
      <label>Deployment model <select value={mode} onChange={e => setMode(e.target.value as typeof mode)}>
        <option value="onprem">Customer-installed server</option>
        <option value="hosted">Hosted customer instance</option>
      </select></label>
      <button onClick={() => setVersion(value => value + 1)}>Run checks</button>
      <button disabled={!report} onClick={() => report && downloadJson(`deployment-readiness-${mode}.json`, report)}>Download report</button>
    </div>
    {error && <p role="alert" className="control-error">{error}</p>}
    {!report && !error && <p role="status">Checking deployment…</p>}
    {report && <>
      <p role="status"><strong>{report.ready ? 'Ready' : 'Not ready for customer deployment'}</strong> · {report.blocking_count} blocking requirements · Checked {new Date(report.checked_at * 1000).toLocaleString()}</p>
      <p>{report.scope}</p>
      <div className="control-table-wrap"><table><thead><tr><th>Requirement</th><th>Status</th><th>Next action / evidence</th></tr></thead>
        <tbody>{report.checks.map(check => <tr key={check.id}><td>{check.title}</td><td><strong className={check.status === 'pass' ? 'status-ok' : 'status-warning'}>{check.status}</strong></td><td>{check.detail}</td></tr>)}</tbody>
      </table></div>
    </>}
  </section>
}
