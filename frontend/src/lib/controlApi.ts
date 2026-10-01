export async function controlApi(path = '', method = 'GET', payload?: unknown) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), method === 'GET' ? 15000 : 60000)
  try {
    const response = await fetch('/api/control' + path, { method, signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: payload ? JSON.stringify(payload) : undefined })
    const data = await response.json().catch(() => null)
    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}). Refresh status and retry.`)
    if (!data) throw new Error('The server returned an invalid response. Refresh status and retry.')
    return data
  } catch (error: any) {
    if (error.name === 'AbortError') throw new Error(method === 'GET' ? 'The server took too long to respond. Try Refresh status.' : 'The operation took too long to respond and may have been applied. Refresh status before retrying.')
    throw error
  } finally { window.clearTimeout(timer) }
}

export function downloadJson(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadCsv(name: string, rows: unknown[][]) {
  const cell = (value: unknown) => {
    let text = String(value ?? '')
    if (/^[\s]*[=+@-]/.test(text)) text = "'" + text
    return '"' + text.replace(/"/g, '""') + '"'
  }
  const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
