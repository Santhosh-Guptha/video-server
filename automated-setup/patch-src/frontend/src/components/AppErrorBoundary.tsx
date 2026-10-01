import { Component, type ReactNode } from 'react'

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <main style={{ maxWidth: 640, margin: '12vh auto', padding: 32, color: '#e2e8f0' }} role="alert"><h1>The workspace could not be displayed</h1><p>Reload to reconnect. Server-side recording and saved camera settings are independent of this page.</p><button className="refreshBtn" onClick={() => window.location.reload()}>Reload application</button></main>
    return this.props.children
  }
}
